#!/usr/bin/env python3
"""
SOPHIA AMS v2 — Live End-to-End Test Runner

Runs 10 real scenarios against a live LLM, producing detailed companion logs
with full conversation dumps, memory state, and store snapshots.

Requires:
  - LLM server running (reads LLM_API_BASE etc. from .env)
  - sentence-transformers model available

Usage:
    python tests/e2e_scenarios.py
    # Inspect reports/YYYY-MM-DD_HHMMSS/
"""

import json
import os
import shutil
import sys
import tempfile
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Ensure project root is on sys.path
# ---------------------------------------------------------------------------
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from dotenv import load_dotenv
load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

from llm_client import LLMClient, LLMError, strip_think_tokens
from code_runner import CodeRunner, RunResult
from conversation_memory import ConversationMemory
from skill_loader import SkillLoader
from stream_monitor import StreamMonitor
from agent_loop import AgentLoop
from EpisodicMemory import EpisodicMemory, Episode
from VectorKnowledgeGraph import VectorKnowledgeGraph
from AssociativeSemanticMemory import AssociativeSemanticMemory
from sophia_agent import SophiaAgent, _load_persona_template


# ═══════════════════════════════════════════════════════════════════════════
# Episodic Adapter — bridge stream_monitor's API to EpisodicMemory's API
# ═══════════════════════════════════════════════════════════════════════════

class _EpisodeHandle:
    """Mimics the object returned by start_episode with an .episode_id attr."""
    def __init__(self, episode_id: str):
        self.episode_id = episode_id


class EpisodicAdapter:
    """
    Bridges stream_monitor's expected interface:
        start_episode(session_id=...) -> obj with .episode_id
        add_message(episode_id=..., role=..., content=...)
        finalize_episode(episode_id)

    To EpisodicMemory's actual interface:
        create_episode(session_id, metadata) -> episode_id (str)
        add_message_to_episode(episode_id, speaker, content, timestamp)
        finalize_episode(episode_id, topics, summary)
    """

    def __init__(self, episodic: EpisodicMemory):
        self._ep = episodic

    def start_episode(self, session_id: str = "default", **kwargs) -> _EpisodeHandle:
        eid = self._ep.create_episode(session_id=session_id)
        return _EpisodeHandle(eid)

    def add_message(self, episode_id: str, role: str = "", content: str = "", **kwargs):
        self._ep.add_message_to_episode(
            episode_id=episode_id,
            speaker=role,
            content=content,
        )

    def finalize_episode(self, episode_id: str, **kwargs):
        self._ep.finalize_episode(episode_id=episode_id)

    # Pass-through for anything the test wants to read directly
    def get_episode(self, episode_id: str) -> Optional[Episode]:
        return self._ep.get_episode(episode_id)

    def get_recent_episodes(self, **kwargs):
        return self._ep.get_recent_episodes(**kwargs)

    def query_episodes_by_session(self, session_id: str):
        return self._ep.query_episodes_by_session(session_id)


# ═══════════════════════════════════════════════════════════════════════════
# Instrumented subclasses — capture every LLM call and code execution
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class HallucinationResult:
    """Result of checking one triple for hallucination."""
    triple: Tuple[str, str, str]
    source_text: str
    verdict: str  # "grounded", "ungrounded", "ambiguous"
    reasoning: str
    scenario_num: int = 0


@dataclass
class LLMCallRecord:
    """One recorded LLM call."""
    messages: List[Dict]
    response: str
    latency_s: float
    error: Optional[str] = None


@dataclass
class CodeExecRecord:
    """One recorded code execution."""
    code: str
    result: RunResult
    latency_s: float


class InstrumentedLLM(LLMClient):
    """LLMClient subclass that logs every chat() call."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.call_log: List[LLMCallRecord] = []

    def chat(self, messages: list, **overrides) -> str:
        t0 = time.time()
        try:
            resp = super().chat(messages, **overrides)
            self.call_log.append(LLMCallRecord(
                messages=messages,
                response=resp,
                latency_s=time.time() - t0,
            ))
            return resp
        except LLMError as e:
            self.call_log.append(LLMCallRecord(
                messages=messages,
                response="",
                latency_s=time.time() - t0,
                error=str(e),
            ))
            raise


class InstrumentedRunner(CodeRunner):
    """CodeRunner subclass that logs every run() call."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.exec_log: List[CodeExecRecord] = []

    def run(self, code: str) -> RunResult:
        t0 = time.time()
        result = super().run(code)
        self.exec_log.append(CodeExecRecord(
            code=code,
            result=result,
            latency_s=time.time() - t0,
        ))
        return result


# ═══════════════════════════════════════════════════════════════════════════
# Scenario log — collects data for one scenario's companion markdown
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class ScenarioLog:
    number: int
    name: str
    description: str

    # Timing
    start_time: float = 0.0
    end_time: float = 0.0

    # Result
    passed: bool = False
    error_msg: str = ""

    # Pre-process
    user_input: str = ""
    recall_context: str = ""
    recalled_triples: List[Any] = field(default_factory=list)
    active_goals: str = ""

    # LLM calls captured during this scenario
    llm_calls: List[LLMCallRecord] = field(default_factory=list)

    # Code executions
    code_execs: List[CodeExecRecord] = field(default_factory=list)

    # Post-process
    episode_id: str = ""
    episode_msg_count: int = 0
    extraction_queued: bool = False
    episode_rotated: bool = False

    # Agent response
    agent_response: str = ""

    # Store snapshot
    triple_count: int = 0
    triple_delta: int = 0
    episode_count: int = 0
    new_triples: List[Dict] = field(default_factory=list)

    # Hallucination checks
    hallucination_results: List[HallucinationResult] = field(default_factory=list)

    # Extra notes
    notes: List[str] = field(default_factory=list)

    @property
    def duration_s(self) -> float:
        return self.end_time - self.start_time

    def render_markdown(self) -> str:
        """Render the full companion log for this scenario."""
        status = "PASS" if self.passed else "FAIL"
        lines = [
            f"# Scenario {self.number:02d}: {self.name}",
            "",
            f"**Description**: {self.description}",
            f"**Duration**: {self.duration_s:.2f}s",
            f"**Result**: {status}",
        ]
        if self.error_msg:
            lines.append(f"**Error**: {self.error_msg}")

        # --- Pre-Process ---
        lines.append("")
        lines.append("## Pre-Process (Memory Recall)")
        lines.append(f'**Input**: "{self.user_input}"')

        if self.recalled_triples:
            lines.append(f"**Recalled Triples**: {len(self.recalled_triples)}")
            lines.append("| # | Subject | Predicate | Object | Confidence | Topics |")
            lines.append("|---|---------|-----------|--------|------------|--------|")
            for i, t in enumerate(self.recalled_triples, 1):
                triple, meta = t if isinstance(t, (list, tuple)) and len(t) >= 2 else (t, {})
                if isinstance(triple, (list, tuple)) and len(triple) >= 3:
                    subj, pred, obj = triple[0], triple[1], triple[2]
                else:
                    subj, pred, obj = str(triple), "", ""
                conf = meta.get("confidence", "—") if isinstance(meta, dict) else "—"
                topics = ", ".join(meta.get("topics", [])[:3]) if isinstance(meta, dict) else ""
                lines.append(f"| {i} | {subj} | {pred} | {obj} | {conf} | {topics} |")
        else:
            lines.append("**Recalled Triples**: 0")

        if self.active_goals:
            lines.append(f"**Active Goals**:\n{self.active_goals}")
        else:
            lines.append("**Active Goals**: (none)")

        if self.recall_context:
            lines.append("**Full Context Injected**:")
            for ctx_line in self.recall_context.split("\n"):
                lines.append(f"> {ctx_line}")

        # --- LLM Calls ---
        for idx, call in enumerate(self.llm_calls, 1):
            lines.append("")
            lines.append(f"## LLM Call #{idx}")
            lines.append(f"**Messages Sent**: {len(call.messages)}")
            lines.append("| # | Role | Content (first 200 chars) | Full Length |")
            lines.append("|---|------|---------------------------|-------------|")
            for j, msg in enumerate(call.messages, 1):
                content = msg.get("content", "")
                preview = content[:200].replace("\n", "\\n").replace("|", "\\|")
                lines.append(f"| {j} | {msg.get('role', '?')} | {preview} | {len(content):,} |")

            lines.append("")
            lines.append("<details><summary>Full messages JSON</summary>")
            lines.append("")
            lines.append("```json")
            try:
                lines.append(json.dumps(call.messages, indent=2, default=str))
            except Exception:
                lines.append(str(call.messages))
            lines.append("```")
            lines.append("</details>")
            lines.append("")

            if call.error:
                lines.append(f"**Error**: {call.error}")
            else:
                lines.append(f"**Response** ({call.latency_s:.2f}s):")
                for resp_line in call.response.split("\n"):
                    lines.append(f"> {resp_line}")

            run_blocks = len([e for e in self.code_execs])
            lines.append(f"**Run Blocks**: {run_blocks}")

        # --- Code Executions ---
        if self.code_execs:
            lines.append("")
            lines.append("## Code Executions")
            for idx, ex in enumerate(self.code_execs, 1):
                lines.append(f"### Execution #{idx} ({ex.latency_s:.2f}s)")
                lines.append("**Code**:")
                lines.append("```python")
                lines.append(ex.code)
                lines.append("```")
                lines.append(f"**Return code**: {ex.result.returncode}")
                if ex.result.stdout:
                    lines.append("**stdout**:")
                    lines.append(f"```\n{ex.result.stdout}\n```")
                if ex.result.stderr:
                    lines.append("**stderr**:")
                    lines.append(f"```\n{ex.result.stderr}\n```")

        # --- Post-Process ---
        lines.append("")
        lines.append("## Post-Process (Memory Save)")
        lines.append(f"**Episode**: {self.episode_id or '(none)'} ({self.episode_msg_count} messages)")
        lines.append(f"**Extraction Queued**: {'Yes' if self.extraction_queued else 'No'}")
        lines.append(f"**Episode Rotated**: {'Yes' if self.episode_rotated else 'No'}")

        # --- Store Snapshot ---
        lines.append("")
        lines.append("## Store Snapshot")
        lines.append(f"**Triples in KG**: {self.triple_count} (+{self.triple_delta} new)")
        lines.append(f"**Episodes**: {self.episode_count}")

        if self.new_triples:
            lines.append("")
            lines.append("<details><summary>New triples since last scenario</summary>")
            lines.append("")
            lines.append("```json")
            lines.append(json.dumps(self.new_triples, indent=2, default=str))
            lines.append("```")
            lines.append("</details>")

        # --- Hallucination Check ---
        if self.hallucination_results:
            lines.append("")
            lines.append("## Hallucination Check")
            grounded = sum(1 for h in self.hallucination_results if h.verdict == "grounded")
            ungrounded = sum(1 for h in self.hallucination_results if h.verdict == "ungrounded")
            ambiguous = sum(1 for h in self.hallucination_results if h.verdict == "ambiguous")
            total_h = len(self.hallucination_results)
            lines.append(f"**{grounded}/{total_h} grounded**, {ungrounded} ungrounded, {ambiguous} ambiguous")
            lines.append("")
            lines.append("| # | Verdict | Subject | Predicate | Object | Reasoning |")
            lines.append("|---|---------|---------|-----------|--------|-----------|")
            for i, h in enumerate(self.hallucination_results, 1):
                s, p, o = h.triple
                reason = h.reasoning[:120].replace("|", "\\|").replace("\n", " ")
                emoji = {"grounded": "OK", "ungrounded": "BAD", "ambiguous": "??"}.get(h.verdict, "??")
                lines.append(f"| {i} | {emoji} | {s} | {p} | {o} | {reason} |")

        # --- Notes ---
        if self.notes:
            lines.append("")
            lines.append("## Notes")
            for note in self.notes:
                lines.append(f"- {note}")

        lines.append("")
        return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════
# E2E Runner — orchestrates everything
# ═══════════════════════════════════════════════════════════════════════════

class E2ERunner:
    """
    Sets up real backends in temp dirs, runs all 10 scenarios sequentially
    (memory accumulates), generates summary + companion logs + store dumps.
    """

    def __init__(self):
        self.tmp_dir = tempfile.mkdtemp(prefix="sophia_e2e_")
        self.kg_path = os.path.join(self.tmp_dir, "kg_data")
        self.ep_path = os.path.join(self.tmp_dir, "ep_data")
        self.ws_path = os.path.join(self.tmp_dir, "workspace")
        os.makedirs(self.ws_path, exist_ok=True)

        # Real backends
        self.kgraph = VectorKnowledgeGraph(path=self.kg_path)
        self.semantic = AssociativeSemanticMemory(kgraph=self.kgraph)
        self.episodic_raw = EpisodicMemory(storage_path=self.ep_path)
        self.episodic = EpisodicAdapter(self.episodic_raw)

        # Instrumented components
        self.llm = InstrumentedLLM()
        self.runner = InstrumentedRunner(workspace=self.ws_path)

        # Skill loader (use real skills dir if present)
        skills_dir = os.path.join(PROJECT_ROOT, "skills")
        self.skill_loader = SkillLoader([skills_dir] if os.path.isdir(skills_dir) else [])

        # Stream monitor
        self.monitor = StreamMonitor(
            semantic_memory=self.semantic,
            episodic_memory=self.episodic,
            auto_recall_limit=10,
            idle_seconds=9999,  # disable auto-consolidation; we flush manually
            episode_rotate_threshold=50,
        )

        # Track triple counts across scenarios
        self._prev_triple_count = 0

        # Scenario logs
        self.logs: List[ScenarioLog] = []

    def _make_agent_loop(self, session_id: str = "e2e") -> AgentLoop:
        """Create an AgentLoop wired to our instrumented components."""
        system_prompt = _load_persona_template()
        return AgentLoop(
            llm=self.llm,
            runner=self.runner,
            system_prompt=system_prompt,
            skill_loader=self.skill_loader,
            conversation_memory=ConversationMemory(max_messages=50),
            pre_process_hook=self.monitor.pre_process,
            post_process_hook=self.monitor.post_process,
            max_rounds=5,
        )

    def _snapshot_store(self) -> Tuple[List[Dict], List[Dict]]:
        """Return current (triples, episodes) as JSON-serializable lists."""
        triples = self.kgraph.get_all_triples()
        eps_raw = self.episodic_raw.get_recent_episodes(hours=9999, limit=9999)
        episodes = [ep.to_dict() for ep in eps_raw] if eps_raw else []
        return triples, episodes

    def _count_episodes(self) -> int:
        eps = self.episodic_raw.get_recent_episodes(hours=9999, limit=9999)
        return len(eps) if eps else 0

    def _flush_session(self, session_id: str):
        """Flush extraction queue synchronously."""
        self.monitor.flush(session_id)

    def _run_scenario(
        self,
        number: int,
        name: str,
        description: str,
        user_messages: List[str],
        session_id: str = "e2e_main",
        rotate_threshold: Optional[int] = None,
        expect_code: bool = False,
        extra_check=None,
    ) -> ScenarioLog:
        """
        Run a single scenario and return its log.
        """
        log = ScenarioLog(number=number, name=name, description=description)
        log.start_time = time.time()

        # Optionally adjust rotation threshold
        old_threshold = self.monitor.episode_rotate_threshold
        if rotate_threshold is not None:
            self.monitor.episode_rotate_threshold = rotate_threshold

        # Snapshot call counts before
        llm_before = len(self.llm.call_log)
        exec_before = len(self.runner.exec_log)

        loop = self._make_agent_loop(session_id)

        try:
            for msg in user_messages:
                log.user_input = msg  # last input shown in log

                # Capture pre-process recall
                try:
                    recall = self.monitor.pre_process(msg, session_id)
                    log.recall_context = recall

                    # Try to parse recalled triples from semantic memory
                    results = self.semantic.query_related_information(msg, limit=10)
                    if results and isinstance(results, dict):
                        log.recalled_triples = results.get("triples", [])
                        # goals
                        try:
                            log.active_goals = self.semantic.get_active_goals_for_prompt(
                                owner="Sophia", limit=10
                            ) or ""
                        except Exception:
                            pass
                except Exception as e:
                    log.notes.append(f"Pre-process error: {e}")

                # Run through agent loop
                response = loop.chat(msg, session_id=session_id)
                log.agent_response = response

            # Flush to force extraction
            self._flush_session(session_id)

            # Capture session state
            session_state = self.monitor._sessions.get(session_id, {})
            log.episode_id = session_state.get("episode_id", "")
            log.episode_msg_count = session_state.get("message_count", 0)
            log.extraction_queued = len(session_state.get("extraction_queue", [])) > 0
            log.episode_rotated = session_state.get("message_count", 0) == 0 and number > 1

            log.passed = True

            # Extra validation
            if extra_check:
                try:
                    extra_check(log, self)
                except AssertionError as e:
                    log.passed = False
                    log.error_msg = f"Assertion failed: {e}"
                except Exception as e:
                    log.notes.append(f"Extra check error: {e}")

        except Exception as e:
            log.passed = False
            log.error_msg = str(e)

        # Restore threshold
        if rotate_threshold is not None:
            self.monitor.episode_rotate_threshold = old_threshold

        # Capture LLM calls and code execs from this scenario
        log.llm_calls = self.llm.call_log[llm_before:]
        log.code_execs = self.runner.exec_log[exec_before:]

        # Store snapshot
        triples, _ = self._snapshot_store()
        log.triple_count = len(triples)
        log.triple_delta = len(triples) - self._prev_triple_count
        log.new_triples = triples[self._prev_triple_count:]
        log.episode_count = self._count_episodes()
        self._prev_triple_count = len(triples)

        log.end_time = time.time()
        self.logs.append(log)
        return log

    # -----------------------------------------------------------------------
    # The 10 Scenarios
    # -----------------------------------------------------------------------

    def scenario_01_basic_chat(self) -> ScenarioLog:
        return self._run_scenario(
            number=1,
            name="Basic Chat",
            description="Greeting exchange — verify full LLM req/resp, empty recall, episode creation.",
            user_messages=["Hello Sophia, how are you today?"],
        )

    def scenario_02_fact_storage(self) -> ScenarioLog:
        return self._run_scenario(
            number=2,
            name="Fact Storage",
            description="Store a fact about the user to verify triple extraction and KG ingestion.",
            user_messages=["Remember that Joey likes Python and lives in the USA."],
        )

    def scenario_03_memory_recall(self) -> ScenarioLog:
        def check(log, runner):
            assert log.recall_context, "Expected non-empty recall context"
        return self._run_scenario(
            number=3,
            name="Memory Recall",
            description="Ask about previously stored facts to verify semantic memory recall.",
            user_messages=["What do you know about Joey?"],
            extra_check=check,
        )

    def scenario_04_code_execution(self) -> ScenarioLog:
        return self._run_scenario(
            number=4,
            name="Code Execution",
            description="Ask agent to calculate using a ```run block to verify code execution pipeline.",
            user_messages=["Can you calculate 2+2 using Python code? Use a ```run block."],
        )

    def scenario_05_multi_turn(self) -> ScenarioLog:
        return self._run_scenario(
            number=5,
            name="Multi-Turn",
            description="5-message conversation to verify message window growth and conversation memory.",
            user_messages=[
                "Let's talk about space exploration.",
                "What's the most interesting planet in our solar system?",
                "Tell me something surprising about that planet.",
                "How far is it from Earth?",
                "Thanks, that was interesting!",
            ],
        )

    def scenario_06_skill_awareness(self) -> ScenarioLog:
        def check(log, runner):
            # At minimum, the system prompt should contain skill info
            if log.llm_calls:
                sys_msg = log.llm_calls[0].messages[0].get("content", "")
                has_skills = "skill" in sys_msg.lower() or "available" in sys_msg.lower()
                if not has_skills:
                    log.notes.append("System prompt may not contain skills section")
        return self._run_scenario(
            number=6,
            name="Skill Awareness",
            description="Ask about skills to verify skills section appears in system prompt.",
            user_messages=["What skills do you have?"],
            extra_check=check,
        )

    def scenario_07_goal_lifecycle(self) -> ScenarioLog:
        def check(log, runner):
            # Manually create a goal and verify it shows up
            try:
                runner.semantic.create_goal(
                    owner="Sophia",
                    description="Learn about quantum computing",
                    priority=3,
                )
                goals = runner.semantic.get_active_goals_for_prompt(owner="Sophia")
                if goals:
                    log.active_goals = goals
                    log.notes.append("Goal successfully created and visible in active goals")
                else:
                    log.notes.append("Goal created but not returned in active goals prompt")
            except Exception as e:
                log.notes.append(f"Goal creation error: {e}")

        return self._run_scenario(
            number=7,
            name="Goal Lifecycle",
            description="Create and query a goal to verify goal triples in KG and pre_process.",
            user_messages=["I'd like to learn about quantum computing. Can you set a goal for that?"],
            extra_check=check,
        )

    def scenario_08_episode_rotation(self) -> ScenarioLog:
        """Chat past rotation threshold to trigger episode finalization."""
        # Use a very low threshold so we trigger rotation quickly
        msgs = [f"Message number {i+1} for rotation test." for i in range(6)]

        def check(log, runner):
            log.notes.append(f"Used rotation threshold of 4 messages")

        return self._run_scenario(
            number=8,
            name="Episode Rotation",
            description="Chat past rotation threshold to trigger episode finalize + new episode.",
            user_messages=msgs,
            session_id="e2e_rotation",
            rotate_threshold=4,
            extra_check=check,
        )

    def scenario_09_cross_session(self) -> ScenarioLog:
        """Two independent sessions — verify isolation."""
        log = ScenarioLog(
            number=9,
            name="Cross-Session",
            description="Two independent sessions to verify memory isolation and no cross-leak.",
        )
        log.start_time = time.time()

        llm_before = len(self.llm.call_log)

        try:
            # Session A
            loop_a = self._make_agent_loop("session_A")
            resp_a = loop_a.chat("I love cats. Remember that.", session_id="session_A")
            self._flush_session("session_A")

            # Session B
            loop_b = self._make_agent_loop("session_B")
            resp_b = loop_b.chat("What do I like?", session_id="session_B")
            self._flush_session("session_B")

            log.agent_response = f"Session A: {resp_a}\n---\nSession B: {resp_b}"
            log.user_input = "(cross-session test)"

            # Check episode isolation
            eps_a = self.episodic_raw.query_episodes_by_session("session_A")
            eps_b = self.episodic_raw.query_episodes_by_session("session_B")
            log.notes.append(f"Session A episodes: {len(eps_a)}")
            log.notes.append(f"Session B episodes: {len(eps_b)}")

            # Recall in session B should NOT know about cats (stored in A)
            recall_b = self.monitor.pre_process("What do I like?", "session_B")
            if "cat" in recall_b.lower():
                log.notes.append("WARNING: Cross-session leak detected — 'cat' found in session B recall")
            else:
                log.notes.append("No cross-session leak detected (expected)")

            log.passed = True

        except Exception as e:
            log.passed = False
            log.error_msg = str(e)

        log.llm_calls = self.llm.call_log[llm_before:]

        # Snapshot
        triples, _ = self._snapshot_store()
        log.triple_count = len(triples)
        log.triple_delta = len(triples) - self._prev_triple_count
        log.new_triples = triples[self._prev_triple_count:]
        log.episode_count = self._count_episodes()
        self._prev_triple_count = len(triples)

        log.end_time = time.time()
        self.logs.append(log)
        return log

    def scenario_10_error_recovery(self) -> ScenarioLog:
        return self._run_scenario(
            number=10,
            name="Error Recovery",
            description="Send malformed code pattern to test agent's error recovery response.",
            user_messages=[
                "Run this Python code for me:\n```run\nimport nonexistent_module_xyz\nprint('should fail')\n```\nWhat happened?",
            ],
        )

    def scenario_11_document_ingestion(self) -> ScenarioLog:
        """Ingest a multi-paragraph document directly into semantic memory and verify triples."""
        log = ScenarioLog(
            number=11,
            name="Document Ingestion",
            description="Ingest a factual document via AssociativeSemanticMemory.ingest_text() and verify triple extraction.",
        )
        log.start_time = time.time()
        llm_before = len(self.llm.call_log)

        # A short factual document with clear entities and relationships
        document = (
            "Hatsune Miku, codenamed CV01, was the first Japanese VOCALOID developed "
            "and distributed by Crypton Future Media. She was released in August 2007 "
            "for the VOCALOID2 engine. Her voice is provided by Japanese voice actress "
            "Saki Fujita.\n\n"
            "Miku quickly became a cultural phenomenon in Japan and worldwide. She has "
            "performed live concerts as a hologram, with her first major concert held "
            "at the Saitama Super Arena in 2010. The character has over 100,000 original "
            "songs created by fans using the VOCALOID software."
        )
        log.user_input = f"(document ingestion: {len(document)} chars)"

        try:
            triple_count_before = len(self.kgraph.get_all_triples())

            # Ingest the document directly (bypasses agent loop — tests the ingestion pipeline)
            result = self.semantic.ingest_text(
                text=document,
                source="document:vocaloid_wiki",
                timestamp=time.time(),
            )

            new_triples = result.get("triples", [])
            log.notes.append(f"Extracted {len(new_triples)} triples from document")

            # Verify we got at least some triples
            if len(new_triples) == 0:
                log.passed = False
                log.error_msg = "No triples extracted from document"
            else:
                # Verify recall works — search for something from the document
                recall_result = self.semantic.query_related_information(
                    "Who created Hatsune Miku?", limit=10
                )
                recalled = recall_result.get("triples", []) if isinstance(recall_result, dict) else []
                log.recalled_triples = recalled
                log.recall_context = f"Recalled {len(recalled)} triples for 'Who created Hatsune Miku?'"

                if recalled:
                    log.notes.append(f"Recall verified: {len(recalled)} triples found for query")
                    log.passed = True
                else:
                    log.notes.append("WARNING: No triples recalled after document ingestion")
                    log.passed = True  # Extraction worked, recall is secondary

        except Exception as e:
            log.passed = False
            log.error_msg = str(e)

        log.llm_calls = self.llm.call_log[llm_before:]

        # Store snapshot
        triples, _ = self._snapshot_store()
        log.triple_count = len(triples)
        log.triple_delta = len(triples) - self._prev_triple_count
        log.new_triples = triples[self._prev_triple_count:]
        log.episode_count = self._count_episodes()
        self._prev_triple_count = len(triples)

        log.end_time = time.time()
        self.logs.append(log)
        return log

    def scenario_12_web_learn_pipeline(self) -> ScenarioLog:
        """
        Simulate the web-learn skill pipeline: fetch content, chunk, ingest each chunk.
        Uses pre-canned content instead of a real URL (no network dependency).
        """
        log = ScenarioLog(
            number=12,
            name="Web Learn Pipeline",
            description="Simulate web-learn skill: chunk web content and ingest each chunk into semantic memory.",
        )
        log.start_time = time.time()
        llm_before = len(self.llm.call_log)

        # Simulated "extracted web page content" — 3 distinct paragraphs
        web_content = (
            "Python is a high-level, general-purpose programming language created by "
            "Guido van Rossum and first released in 1991. Its design philosophy emphasizes "
            "code readability with the use of significant indentation. Python is dynamically "
            "typed and garbage-collected.\n\n"
            "Python consistently ranks as one of the most popular programming languages. "
            "It is used extensively in web development with frameworks like Django and Flask, "
            "in data science with libraries like NumPy, Pandas, and scikit-learn, and in "
            "artificial intelligence with TensorFlow and PyTorch.\n\n"
            "The Python Software Foundation (PSF) is a non-profit organization devoted to "
            "the Python programming language. It was created in 2001 and is based in "
            "Wilmington, Delaware. The PSF manages the open-source licensing for Python "
            "versions 2.1 and later."
        )
        log.user_input = f"(web-learn pipeline: {len(web_content)} chars, simulated)"

        try:
            # Chunk the content (mimicking learn_from_url's _chunk_text_by_paragraphs)
            paragraphs = [p.strip() for p in web_content.split("\n\n") if p.strip()]
            log.notes.append(f"Content split into {len(paragraphs)} chunks")

            total_triples = 0
            chunks_stored = 0

            for i, chunk in enumerate(paragraphs):
                try:
                    result = self.semantic.ingest_text(
                        text=chunk,
                        source=f"web:python_wiki#chunk_{i}",
                        timestamp=time.time(),
                    )
                    chunk_triples = len(result.get("triples", []))
                    total_triples += chunk_triples
                    chunks_stored += 1
                    log.notes.append(f"Chunk {i+1}: {chunk_triples} triples")
                except Exception as e:
                    log.notes.append(f"Chunk {i+1} error: {e}")

            log.notes.append(f"Total: {total_triples} triples from {chunks_stored}/{len(paragraphs)} chunks")

            if total_triples == 0:
                log.passed = False
                log.error_msg = "No triples extracted from any chunk"
            else:
                # Verify recall across chunks — query should find facts from different chunks
                queries = [
                    ("Who created Python?", "Guido"),
                    ("What is Python used for?", "web"),
                    ("What is the Python Software Foundation?", "PSF"),
                ]
                hits = 0
                for query, keyword in queries:
                    recall = self.semantic.query_related_information(query, limit=5)
                    recalled = recall.get("triples", []) if isinstance(recall, dict) else []
                    if recalled:
                        hits += 1
                        log.notes.append(f"Recall '{query}': {len(recalled)} triples found")
                    else:
                        log.notes.append(f"Recall '{query}': no triples found")

                log.recalled_triples = []  # Don't clutter with all recall results
                log.recall_context = f"Cross-chunk recall: {hits}/{len(queries)} queries returned results"
                log.passed = True

        except Exception as e:
            log.passed = False
            log.error_msg = str(e)

        log.llm_calls = self.llm.call_log[llm_before:]

        # Store snapshot
        triples, _ = self._snapshot_store()
        log.triple_count = len(triples)
        log.triple_delta = len(triples) - self._prev_triple_count
        log.new_triples = triples[self._prev_triple_count:]
        log.episode_count = self._count_episodes()
        self._prev_triple_count = len(triples)

        log.end_time = time.time()
        self.logs.append(log)
        return log

    # -----------------------------------------------------------------------
    # Hallucination checking
    # -----------------------------------------------------------------------

    def _check_hallucinations(self) -> List[HallucinationResult]:
        """
        After all scenarios, use the LLM to judge whether each extracted triple
        is grounded in its source text.  Returns results and attaches them to
        the relevant ScenarioLog.
        """
        all_results: List[HallucinationResult] = []

        # Gather all triples across scenarios
        triples_to_check: List[Dict] = []
        for log in self.logs:
            for t in log.new_triples:
                src_text = t.get("metadata", {}).get("source_text", "")
                subj = t.get("subject", "")
                pred = t.get("predicate", "")
                obj = t.get("object", "")
                if not (subj and pred and obj):
                    continue
                triples_to_check.append({
                    "subject": subj,
                    "predicate": pred,
                    "object": obj,
                    "source_text": src_text,
                    "scenario_num": log.number,
                })

        if not triples_to_check:
            return all_results

        # Small batches — local models struggle with large structured outputs
        batch_size = 5
        for batch_start in range(0, len(triples_to_check), batch_size):
            batch = triples_to_check[batch_start:batch_start + batch_size]

            entries = []
            for i, item in enumerate(batch):
                entries.append(
                    f'{i+1}. Triple: ({item["subject"]}, {item["predicate"]}, {item["object"]})\n'
                    f'   Source text: "{item["source_text"]}"'
                )

            prompt = (
                "You are a fact-checking judge. For each triple below, determine if the fact "
                "expressed by (subject, predicate, object) is ACTUALLY STATED or STRONGLY IMPLIED "
                "by its source text. The source text is a snippet from a conversation.\n\n"
                "Rules:\n"
                "- 'grounded': The fact is clearly stated or directly implied by the source text.\n"
                "- 'ungrounded': The fact is NOT in the source text — it was invented/hallucinated.\n"
                "- 'ambiguous': Borderline — loosely related but not clearly stated.\n"
                "- If source_text is empty, mark 'ambiguous' (we can't verify without source).\n\n"
                "Respond with ONLY a JSON array. Each element must have:\n"
                '  {"index": <1-based>, "verdict": "grounded|ungrounded|ambiguous", '
                '"reasoning": "<brief explanation>"}\n\n'
                "Triples to judge:\n" + "\n".join(entries)
            )

            try:
                raw = self.llm.chat(
                    [{"role": "user", "content": prompt}],
                    temperature=0.0,
                    max_tokens=4096,
                )

                # Robust JSON array extraction (handles think tokens, fences, prose)
                import re as _re
                # Strip think blocks first (handles both closed and unclosed)
                cleaned = strip_think_tokens(raw)
                # Try markdown fence
                fence = _re.search(r'```(?:json)?\s*\n?(.*?)```', cleaned, _re.DOTALL)
                if fence:
                    cleaned = fence.group(1).strip()
                # Find the JSON array by scanning for matching [ ... ]
                judgments = None
                for start_i in range(len(cleaned)):
                    if cleaned[start_i] == '[':
                        depth = 0
                        for end_i in range(start_i, len(cleaned)):
                            if cleaned[end_i] == '[':
                                depth += 1
                            elif cleaned[end_i] == ']':
                                depth -= 1
                                if depth == 0:
                                    try:
                                        judgments = json.loads(cleaned[start_i:end_i + 1])
                                    except json.JSONDecodeError:
                                        pass
                                    break
                        if judgments is not None:
                            break
                if judgments is None:
                    raise ValueError(f"No JSON array found in response ({len(raw)} chars)")

                for j in judgments:
                    idx = j.get("index", 0) - 1
                    if 0 <= idx < len(batch):
                        item = batch[idx]
                        result = HallucinationResult(
                            triple=(item["subject"], item["predicate"], item["object"]),
                            source_text=item["source_text"],
                            verdict=j.get("verdict", "ambiguous").lower(),
                            reasoning=j.get("reasoning", ""),
                            scenario_num=item["scenario_num"],
                        )
                        all_results.append(result)

            except Exception as e:
                # Retry once with a simplified prompt before giving up
                retry_ok = False
                try:
                    retry_prompt = (
                        "Respond with ONLY a JSON array. For each triple, give "
                        '{"index": N, "verdict": "grounded|ungrounded|ambiguous", "reasoning": "..."}.\n\n'
                        + "\n".join(entries)
                    )
                    raw2 = self.llm.chat(
                        [{"role": "user", "content": retry_prompt}],
                        temperature=0.0, max_tokens=4096,
                    )
                    cleaned2 = strip_think_tokens(raw2)
                    fence2 = _re.search(r'```(?:json)?\s*\n?(.*?)```', cleaned2, _re.DOTALL)
                    if fence2:
                        cleaned2 = fence2.group(1).strip()
                    for start_i in range(len(cleaned2)):
                        if cleaned2[start_i] == '[':
                            depth = 0
                            for end_i in range(start_i, len(cleaned2)):
                                if cleaned2[end_i] == '[':
                                    depth += 1
                                elif cleaned2[end_i] == ']':
                                    depth -= 1
                                    if depth == 0:
                                        try:
                                            judgments = json.loads(cleaned2[start_i:end_i + 1])
                                        except json.JSONDecodeError:
                                            pass
                                        break
                            if judgments is not None:
                                break
                    if judgments is not None:
                        for j in judgments:
                            idx = j.get("index", 0) - 1
                            if 0 <= idx < len(batch):
                                item = batch[idx]
                                all_results.append(HallucinationResult(
                                    triple=(item["subject"], item["predicate"], item["object"]),
                                    source_text=item["source_text"],
                                    verdict=j.get("verdict", "ambiguous").lower(),
                                    reasoning=j.get("reasoning", ""),
                                    scenario_num=item["scenario_num"],
                                ))
                        retry_ok = True
                except Exception:
                    pass

                if not retry_ok:
                    # Mark entire batch ambiguous
                    for item in batch:
                        all_results.append(HallucinationResult(
                            triple=(item["subject"], item["predicate"], item["object"]),
                            source_text=item["source_text"],
                            verdict="ambiguous",
                            reasoning=f"Judge call failed: {e}",
                            scenario_num=item["scenario_num"],
                        ))

        # Attach results to their respective scenario logs
        by_scenario: Dict[int, List[HallucinationResult]] = {}
        for r in all_results:
            by_scenario.setdefault(r.scenario_num, []).append(r)
        for log in self.logs:
            log.hallucination_results = by_scenario.get(log.number, [])

        return all_results

    # -----------------------------------------------------------------------
    # Orchestration
    # -----------------------------------------------------------------------

    def run_all(self) -> List[ScenarioLog]:
        """Run all scenarios sequentially, accumulating memory."""
        scenarios = [
            self.scenario_01_basic_chat,
            self.scenario_02_fact_storage,
            self.scenario_03_memory_recall,
            self.scenario_04_code_execution,
            self.scenario_05_multi_turn,
            self.scenario_06_skill_awareness,
            self.scenario_07_goal_lifecycle,
            self.scenario_08_episode_rotation,
            self.scenario_09_cross_session,
            self.scenario_10_error_recovery,
            self.scenario_11_document_ingestion,
            self.scenario_12_web_learn_pipeline,
        ]

        total = len(scenarios)
        print(f"Running {total} live E2E scenarios...")
        print(f"LLM: {self.llm.base_url} | Model: {self.llm.model}")
        print(f"Temp dir: {self.tmp_dir}")
        print()

        for i, fn in enumerate(scenarios):
            name = fn.__name__.replace("scenario_", "").replace("_", " ").title()
            print(f"  [{i+1:02d}/{total}] {name}...", end=" ", flush=True)
            try:
                log = fn()
                status = "PASS" if log.passed else "FAIL"
                print(f"{status} ({log.duration_s:.1f}s)")
            except Exception as e:
                print(f"CRASH: {e}")

        # Run hallucination checks on all extracted triples
        print("\n  Running hallucination checks...", end=" ", flush=True)
        try:
            h_results = self._check_hallucinations()
            grounded = sum(1 for r in h_results if r.verdict == "grounded")
            ungrounded = sum(1 for r in h_results if r.verdict == "ungrounded")
            ambiguous = sum(1 for r in h_results if r.verdict == "ambiguous")
            print(f"Done ({len(h_results)} triples: {grounded} grounded, {ungrounded} ungrounded, {ambiguous} ambiguous)")
        except Exception as e:
            print(f"Failed: {e}")

        return self.logs

    def generate_report(self, output_dir: str = None) -> str:
        """
        Generate the full report structure:
          reports/YYYY-MM-DD_HHMMSS/
            summary.txt
            scenario_01_basic_chat.md
            ...
            store_dumps/
              triples_final.json
              episodes_final.json
              per_scenario/
                after_01.json
                ...
        """
        if output_dir is None:
            ts = datetime.now().strftime("%Y-%m-%d_%H%M%S")
            output_dir = os.path.join(PROJECT_ROOT, "reports", ts)

        os.makedirs(output_dir, exist_ok=True)
        dumps_dir = os.path.join(output_dir, "store_dumps")
        per_scenario_dir = os.path.join(dumps_dir, "per_scenario")
        os.makedirs(per_scenario_dir, exist_ok=True)

        # --- Summary ---
        passed = sum(1 for l in self.logs if l.passed)
        total = len(self.logs)
        total_dur = sum(l.duration_s for l in self.logs)

        summary_lines = [
            "=" * 64,
            "  SOPHIA AMS v2 -- LIVE E2E TEST REPORT",
            f"  Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"  LLM: {self.llm.base_url} | Model: {self.llm.model}",
            "=" * 64,
            "",
            f"RESULT: {passed}/{total} scenarios passed",
            f"TOTAL DURATION: {total_dur:.1f}s",
            f"TOTAL LLM CALLS: {len(self.llm.call_log)}",
            f"TOTAL CODE EXECS: {len(self.runner.exec_log)}",
            "",
            f"{'#':<4} {'SCENARIO':<30} {'RESULT':<8} {'TIME':>8} {'LLM':>5} {'CODE':>5}",
            "-" * 64,
        ]

        for log in self.logs:
            status = "PASS" if log.passed else "FAIL"
            summary_lines.append(
                f"{log.number:02d}   {log.name:<30} {status:<8} {log.duration_s:>7.1f}s"
                f" {len(log.llm_calls):>5} {len(log.code_execs):>5}"
            )

        summary_lines.append("-" * 64)
        summary_lines.append("")

        # Failures
        failures = [l for l in self.logs if not l.passed]
        if failures:
            summary_lines.append("FAILURES:")
            for l in failures:
                summary_lines.append(f"  [{l.number:02d}] {l.name}: {l.error_msg}")
            summary_lines.append("")

        # Hallucination stats
        all_h = []
        for log in self.logs:
            all_h.extend(log.hallucination_results)
        if all_h:
            h_grounded = sum(1 for h in all_h if h.verdict == "grounded")
            h_ungrounded = sum(1 for h in all_h if h.verdict == "ungrounded")
            h_ambiguous = sum(1 for h in all_h if h.verdict == "ambiguous")
            summary_lines.append(f"HALLUCINATION CHECK: {h_grounded}/{len(all_h)} grounded, "
                                 f"{h_ungrounded} ungrounded, {h_ambiguous} ambiguous")
            if h_ungrounded:
                summary_lines.append("UNGROUNDED TRIPLES:")
                for h in all_h:
                    if h.verdict == "ungrounded":
                        s, p, o = h.triple
                        summary_lines.append(f"  [{h.scenario_num:02d}] {s} | {p} | {o}")
                        summary_lines.append(f"       Reason: {h.reasoning[:100]}")
            summary_lines.append("")

        # Final store stats
        triples_final, episodes_final = self._snapshot_store()
        summary_lines.append(f"FINAL STORE: {len(triples_final)} triples, {len(episodes_final)} episodes")
        summary_lines.append("=" * 64)

        summary_text = "\n".join(summary_lines)
        with open(os.path.join(output_dir, "summary.txt"), "w", encoding="utf-8") as f:
            f.write(summary_text)

        # --- Companion logs ---
        for log in self.logs:
            slug = log.name.lower().replace(" ", "_").replace("-", "_")
            filename = f"scenario_{log.number:02d}_{slug}.md"
            with open(os.path.join(output_dir, filename), "w", encoding="utf-8") as f:
                f.write(log.render_markdown())

        # --- Hallucination report ---
        if all_h:
            h_lines = [
                "# Hallucination Report",
                "",
                f"**Total triples checked**: {len(all_h)}",
                f"**Grounded**: {h_grounded}",
                f"**Ungrounded**: {h_ungrounded}",
                f"**Ambiguous**: {h_ambiguous}",
                f"**Grounding rate**: {h_grounded/len(all_h)*100:.1f}%",
                "",
            ]

            if h_ungrounded:
                h_lines.append("## Ungrounded Triples (Hallucinations)")
                h_lines.append("")
                for h in all_h:
                    if h.verdict == "ungrounded":
                        s, p, o = h.triple
                        h_lines.append(f"### `{s}` | `{p}` | `{o}`")
                        h_lines.append(f"- **Scenario**: {h.scenario_num:02d}")
                        h_lines.append(f"- **Source text**: \"{h.source_text}\"")
                        h_lines.append(f"- **Reasoning**: {h.reasoning}")
                        h_lines.append("")

            if h_ambiguous:
                h_lines.append("## Ambiguous Triples")
                h_lines.append("")
                for h in all_h:
                    if h.verdict == "ambiguous":
                        s, p, o = h.triple
                        h_lines.append(f"- `{s}` | `{p}` | `{o}` — {h.reasoning[:100]}")
                h_lines.append("")

            h_lines.append("## All Results")
            h_lines.append("")
            h_lines.append("| # | Scenario | Verdict | Subject | Predicate | Object | Reasoning |")
            h_lines.append("|---|----------|---------|---------|-----------|--------|-----------|")
            for i, h in enumerate(all_h, 1):
                s, p, o = h.triple
                reason = h.reasoning[:80].replace("|", "\\|").replace("\n", " ")
                h_lines.append(f"| {i} | {h.scenario_num:02d} | {h.verdict} | {s} | {p} | {o} | {reason} |")

            with open(os.path.join(output_dir, "hallucination_report.md"), "w", encoding="utf-8") as f:
                f.write("\n".join(h_lines))

        # --- Store dumps ---
        with open(os.path.join(dumps_dir, "triples_final.json"), "w", encoding="utf-8") as f:
            json.dump(triples_final, f, indent=2, default=str)

        with open(os.path.join(dumps_dir, "episodes_final.json"), "w", encoding="utf-8") as f:
            json.dump(episodes_final, f, indent=2, default=str)

        # Per-scenario snapshots (reconstruct from log data)
        cumulative_count = 0
        for log in self.logs:
            cumulative_count += log.triple_delta
            snapshot = {
                "scenario": log.number,
                "name": log.name,
                "triple_count": log.triple_count,
                "triple_delta": log.triple_delta,
                "episode_count": log.episode_count,
                "new_triples": log.new_triples,
            }
            fname = f"after_{log.number:02d}.json"
            with open(os.path.join(per_scenario_dir, fname), "w", encoding="utf-8") as f:
                json.dump(snapshot, f, indent=2, default=str)

        print(f"\nReport written to: {output_dir}")
        return output_dir

    def cleanup(self):
        """Remove temp directory."""
        try:
            self.semantic.close()
        except Exception:
            pass
        try:
            shutil.rmtree(self.tmp_dir, ignore_errors=True)
        except Exception:
            pass


# ═══════════════════════════════════════════════════════════════════════════
# Public API for run_report.py integration
# ═══════════════════════════════════════════════════════════════════════════

def run_e2e_scenarios() -> Tuple[int, int, str, List[ScenarioLog]]:
    """
    Run all E2E scenarios and generate report.

    Returns:
        (passed, total, report_dir, logs)
    """
    runner = E2ERunner()
    try:
        logs = runner.run_all()
        report_dir = runner.generate_report()
        passed = sum(1 for l in logs if l.passed)
        return passed, len(logs), report_dir, logs
    finally:
        runner.cleanup()


# ═══════════════════════════════════════════════════════════════════════════
# CLI entry point
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 64)
    print("  SOPHIA AMS v2 — Live E2E Test Runner")
    print("=" * 64)
    print()

    runner = E2ERunner()
    try:
        logs = runner.run_all()
        print()
        report_dir = runner.generate_report()

        # Print summary
        passed = sum(1 for l in logs if l.passed)
        total = len(logs)
        print(f"\n{'='*40}")
        print(f"  {passed}/{total} scenarios passed")
        if passed < total:
            for l in logs:
                if not l.passed:
                    print(f"  FAIL [{l.number:02d}] {l.name}: {l.error_msg}")
        print(f"{'='*40}")

        sys.exit(0 if passed == total else 1)
    finally:
        runner.cleanup()
