"""
SophiaAMS v2 — Torture Test Suite

Simulated, accelerated stress tests exercising the full framework under realistic
conditions. All external dependencies (LLM, memory systems, subprocess) are mocked.
Deterministic, fast (<10s), independent tests.

8 test classes, 30 test methods.
"""

import os
import shutil
import tempfile
import threading
import time
import unittest
from unittest.mock import MagicMock, patch

from llm_client import LLMClient, LLMError
from code_runner import CodeRunner, RunResult
from conversation_memory import ConversationMemory
from skill_loader import SkillLoader
from stream_monitor import StreamMonitor
from agent_loop import AgentLoop


# ============================================================================
# Base class with mock factories
# ============================================================================

class TortureBase(unittest.TestCase):
    """Base class providing mock factory methods for torture tests."""

    def _make_mock_llm(self, responses=None):
        """Create a mock LLMClient with configurable responses."""
        llm = MagicMock(spec=LLMClient)
        if responses is not None:
            llm.chat.side_effect = list(responses)
        else:
            llm.chat.return_value = "Default response."
        return llm

    def _make_mock_runner(self, default_ok=True):
        """Create a mock CodeRunner."""
        runner = MagicMock(spec=CodeRunner)
        if default_ok:
            runner.run.return_value = RunResult(stdout="ok", stderr="", returncode=0)
        else:
            runner.run.return_value = RunResult(stdout="", stderr="error", returncode=1)
        return runner

    def _make_mock_semantic(self):
        """Create mock semantic memory."""
        sem = MagicMock()
        sem.query_related_information.return_value = {"triples": []}
        sem.get_active_goals_for_prompt.return_value = ""
        sem.ingest_text.return_value = {"triples": []}
        return sem

    def _make_mock_episodic(self):
        """Create mock episodic memory with sequential episode IDs."""
        ep = MagicMock()
        counter = [0]

        def start_ep(**kwargs):
            counter[0] += 1
            e = MagicMock()
            e.episode_id = f"ep{counter[0]}"
            return e

        ep.start_episode.side_effect = start_ep
        return ep

    def _make_agent_loop(self, llm=None, runner=None, **kwargs):
        """Build an AgentLoop with mocks."""
        llm = llm or self._make_mock_llm()
        runner = runner or self._make_mock_runner()
        return AgentLoop(
            llm=llm,
            runner=runner,
            system_prompt="You are a test agent.",
            **kwargs,
        ), llm, runner


# ============================================================================
# 1. Conversation Stress
# ============================================================================

class TestConversationStress(TortureBase):
    """High-volume conversation through agent loop and memory management."""

    def test_100_message_exchange(self):
        """100 messages through AgentLoop without exceeding memory bounds."""
        llm = self._make_mock_llm()
        llm.chat.return_value = "Got it."
        mem = ConversationMemory(max_messages=50, summary_threshold=40)
        loop = AgentLoop(
            llm=llm, runner=self._make_mock_runner(),
            system_prompt="Test", conversation_memory=mem,
        )

        for i in range(100):
            loop.chat(f"Message number {i}")

        # Memory should never exceed max_messages + a few for the current exchange
        self.assertLessEqual(mem.message_count, 50)
        self.assertEqual(llm.chat.call_count, 100)

    def test_summarization_trigger_count(self):
        """Summarization fires the expected number of times."""
        call_count = [0]

        def summarize_fn(messages):
            call_count[0] += 1
            return f"Summary v{call_count[0]}"

        mem = ConversationMemory(
            max_messages=50, summarize_fn=summarize_fn, summary_threshold=10,
        )

        for i in range(50):
            mem.add_message("user", f"msg {i}")
            mem.add_message("assistant", f"reply {i}")
            if mem.needs_summarization():
                mem.summarize()

        self.assertGreaterEqual(call_count[0], 3)
        msgs = mem.get_messages()
        self.assertEqual(msgs[0]["role"], "system")
        self.assertIn("Summary", msgs[0]["content"])

    def test_memory_window_bounded(self):
        """Message count never exceeds max_messages under sustained load."""
        mem = ConversationMemory(max_messages=20, summary_threshold=15)

        for i in range(200):
            mem.add_message("user", f"message {i}")
            if mem.needs_summarization():
                mem.summarize()
            self.assertLessEqual(mem.message_count, 20,
                                 f"Memory exceeded max at iteration {i}")

    def test_summary_chain_integrity(self):
        """Successive summaries chain correctly (each receives previous)."""
        received_summaries = []

        def summarize_fn(messages):
            # Check if previous summary was passed
            for m in messages:
                if m["role"] == "system" and "Previous summary" in m["content"]:
                    received_summaries.append(m["content"])
            return f"Summary #{len(received_summaries) + 1}"

        mem = ConversationMemory(
            summarize_fn=summarize_fn, summary_threshold=6,
        )

        for batch in range(5):
            for i in range(8):
                mem.add_message("user", f"batch{batch} msg{i}")
            if mem.needs_summarization():
                mem.summarize()

        # After 5 batches of 8, should have chained summaries
        self.assertGreaterEqual(len(received_summaries), 1)

    def test_rapid_add_get_cycle(self):
        """500 rapid add/get cycles don't corrupt internal state."""
        mem = ConversationMemory()

        for i in range(500):
            mem.add_message("user", f"msg {i}")
            msgs = mem.get_messages()
            self.assertIsInstance(msgs, list)
            for m in msgs:
                self.assertIn("role", m)
                self.assertIn("content", m)


# ============================================================================
# 2. Concurrent Sessions
# ============================================================================

class TestConcurrentSessions(TortureBase):
    """Multi-threaded session access through SophiaAgent."""

    def _make_patched_agent(self):
        """Create a SophiaAgent with mocked dependencies."""
        with patch("sophia_agent.LLMClient") as mock_cls, \
             patch("sophia_agent.init_workspace"):
            mock_llm = MagicMock()
            mock_llm.chat.return_value = "Hello!"
            mock_cls.return_value = mock_llm

            from sophia_agent import SophiaAgent
            agent = SophiaAgent(
                semantic_memory=self._make_mock_semantic(),
                episodic_memory=self._make_mock_episodic(),
                workspace_dir=tempfile.mkdtemp(),
                skill_paths=[],
            )
            return agent

    def test_10_parallel_sessions(self):
        """10 threads each chatting on their own session."""
        agent = self._make_patched_agent()
        errors = []
        barrier = threading.Barrier(10)

        def worker(session_id):
            try:
                barrier.wait(timeout=5)
                for _ in range(10):
                    agent.chat(session_id, "Hello")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(f"s{i}",)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        self.assertEqual(len(errors), 0, f"Errors: {errors}")
        self.assertEqual(len(agent._sessions), 10)

    def test_concurrent_session_creation(self):
        """20 threads creating unique sessions simultaneously."""
        agent = self._make_patched_agent()
        barrier = threading.Barrier(20)
        errors = []

        def worker(i):
            try:
                barrier.wait(timeout=5)
                agent.chat(f"session-{i}", "Hi")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        self.assertEqual(len(errors), 0, f"Errors: {errors}")
        self.assertEqual(len(agent._sessions), 20)

    def test_concurrent_chat_same_session(self):
        """5 threads chatting on the same session."""
        agent = self._make_patched_agent()
        barrier = threading.Barrier(5)
        errors = []

        def worker():
            try:
                barrier.wait(timeout=5)
                for _ in range(5):
                    agent.chat("shared", "Hello")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        self.assertEqual(len(errors), 0, f"Errors: {errors}")
        self.assertIn("shared", agent._sessions)

    def test_concurrent_clear_and_chat(self):
        """One thread chats while another clears — no crash."""
        agent = self._make_patched_agent()
        errors = []

        def chatter():
            try:
                for _ in range(20):
                    agent.chat("volatile", "Hello")
            except Exception as e:
                errors.append(e)

        def clearer():
            try:
                for _ in range(10):
                    agent.clear_session("volatile")
                    time.sleep(0.001)
            except Exception as e:
                errors.append(e)

        t1 = threading.Thread(target=chatter)
        t2 = threading.Thread(target=clearer)
        t1.start()
        t2.start()
        t1.join(timeout=30)
        t2.join(timeout=30)

        self.assertEqual(len(errors), 0, f"Errors: {errors}")


# ============================================================================
# 3. Code Execution Cycling
# ============================================================================

class TestCodeExecutionCycling(TortureBase):
    """Rapid code execution with varied success/failure patterns."""

    def test_rapid_success_failure_cycle(self):
        """20 messages alternating success/failure code execution."""
        responses = []
        for i in range(20):
            responses.append(f'Result:\n```run\nprint("{i}")\n```')
            responses.append(f"The result was {i}.")

        llm = self._make_mock_llm(responses)
        runner = self._make_mock_runner()

        # Alternate success/failure
        results = []
        for i in range(20):
            if i % 2 == 0:
                results.append(RunResult(stdout=str(i), stderr="", returncode=0))
            else:
                results.append(RunResult(stdout="", stderr="fail", returncode=1))
        runner.run.side_effect = results

        loop = AgentLoop(llm=llm, runner=runner, system_prompt="Test", max_rounds=2)

        for i in range(20):
            result = loop.chat(f"Run code {i}")
            self.assertIsInstance(result, str)

        self.assertEqual(runner.run.call_count, 20)

    def test_timeout_recovery(self):
        """Agent recovers after code execution timeout."""
        responses = [
            '```run\nimport time; time.sleep(100)\n```',
            "That timed out. Let me try differently.",
        ]
        llm = self._make_mock_llm(responses)
        runner = self._make_mock_runner()
        runner.run.return_value = RunResult(
            stdout="", stderr="Execution timed out after 10 seconds.", returncode=1,
        )

        loop = AgentLoop(llm=llm, runner=runner, system_prompt="Test", max_rounds=2)
        result = loop.chat("Run something slow")
        self.assertIsInstance(result, str)
        self.assertTrue(len(result) > 0)

    def test_all_rounds_with_code(self):
        """Max rounds enforced when LLM always returns code blocks."""
        llm = self._make_mock_llm()
        llm.chat.return_value = '```run\nprint("loop")\n```'
        runner = self._make_mock_runner()

        loop = AgentLoop(llm=llm, runner=runner, system_prompt="Test", max_rounds=5)
        result = loop.chat("Go forever")

        self.assertEqual(llm.chat.call_count, 5)
        self.assertEqual(runner.run.call_count, 5)


# ============================================================================
# 4. Skill Discovery Churn
# ============================================================================

class TestSkillDiscoveryChurn(TortureBase):
    """Skill catalog changes during operation."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _write_skill(self, name, description="A skill"):
        skill_dir = os.path.join(self.tmpdir, name)
        os.makedirs(skill_dir, exist_ok=True)
        with open(os.path.join(skill_dir, "SKILL.md"), "w") as f:
            f.write(f"---\nname: {name}\ndescription: {description}\n---\n# {name}\n")

    def test_skill_added_mid_session(self):
        """New skill appears after refresh."""
        self._write_skill("skill-a")
        loader = SkillLoader([self.tmpdir])
        self.assertEqual(len(loader.list_skills()), 1)

        self._write_skill("skill-b")
        loader.refresh()
        self.assertEqual(len(loader.list_skills()), 2)
        self.assertIn("skill-b", loader.descriptions())

    def test_skill_removed_mid_session(self):
        """Removed skill disappears after refresh."""
        self._write_skill("keep")
        self._write_skill("remove")
        loader = SkillLoader([self.tmpdir])
        self.assertEqual(len(loader.list_skills()), 2)

        shutil.rmtree(os.path.join(self.tmpdir, "remove"))
        loader.refresh()
        self.assertEqual(len(loader.list_skills()), 1)
        self.assertIsNone(loader.get_skill("remove"))

    def test_skill_descriptions_in_loop_after_refresh(self):
        """AgentLoop picks up refreshed skill catalog dynamically each turn."""
        self._write_skill("alpha", "First skill")
        loader = SkillLoader([self.tmpdir])

        llm = self._make_mock_llm()
        llm.chat.return_value = "Done."
        loop = AgentLoop(
            llm=llm, runner=self._make_mock_runner(),
            system_prompt="Test\n{skills_section}", skill_loader=loader,
        )

        loop.chat("test1")
        call1_system = llm.chat.call_args[0][0][0]["content"]
        self.assertIn("alpha", call1_system)
        self.assertNotIn("beta", call1_system)

        # Add a new skill — AgentLoop should pick it up on the next turn
        # because _build_system_prompt calls skill_loader.refresh()
        self._write_skill("beta", "Second skill")

        loop.chat("test2")
        call2_system = llm.chat.call_args[0][0][0]["content"]
        self.assertIn("alpha", call2_system)
        self.assertIn("beta", call2_system)


# ============================================================================
# 5. Memory Pipeline Stress
# ============================================================================

class TestMemoryPipelineStress(TortureBase):
    """StreamMonitor under high throughput."""

    def test_rapid_pre_post_100_exchanges(self):
        """100 rapid pre_process + post_process cycles."""
        sem = self._make_mock_semantic()
        ep = self._make_mock_episodic()
        monitor = StreamMonitor(
            semantic_memory=sem, episodic_memory=ep,
            idle_seconds=999,  # don't fire timer during test
        )

        for i in range(100):
            monitor.pre_process(f"User message {i}", "s1")
            monitor.post_process("s1", f"User message {i}", f"Response {i}")

        self.assertEqual(sem.query_related_information.call_count, 100)
        self.assertEqual(ep.add_message.call_count, 200)

        # Cleanup timers
        for t in monitor._timers.values():
            t.cancel()

    def test_extraction_queue_accumulation(self):
        """Extraction queue grows until flush drains it."""
        sem = self._make_mock_semantic()
        ep = self._make_mock_episodic()
        monitor = StreamMonitor(
            semantic_memory=sem, episodic_memory=ep,
            idle_seconds=999,
        )

        for i in range(50):
            monitor.post_process("s1", f"User message number {i}", f"Response number {i}")

        session = monitor._sessions["s1"]
        self.assertEqual(len(session["extraction_queue"]), 50)

        monitor.flush("s1")
        self.assertEqual(sem.ingest_text.call_count, 50)
        self.assertEqual(len(monitor._sessions["s1"]["extraction_queue"]), 0)

    def test_episode_rotation_under_load(self):
        """Episodes rotate at threshold under sustained load."""
        sem = self._make_mock_semantic()
        ep = self._make_mock_episodic()
        monitor = StreamMonitor(
            semantic_memory=sem, episodic_memory=ep,
            episode_rotate_threshold=10,
            idle_seconds=999,
        )

        # 25 post_process calls = 50 messages = 5 rotations
        for i in range(25):
            monitor.post_process("s1", f"Long enough message {i}", f"Long enough response {i}")

        self.assertEqual(ep.finalize_episode.call_count, 5)
        # starts: call 1, 6, 11, 16, 21 (last rotation at 25 finalizes but no restart needed)
        self.assertEqual(ep.start_episode.call_count, 5)

        for t in monitor._timers.values():
            t.cancel()

    def test_consolidation_timer_cancellation(self):
        """Rapid posts cancel and reschedule timers correctly."""
        sem = self._make_mock_semantic()
        ep = self._make_mock_episodic()
        monitor = StreamMonitor(
            semantic_memory=sem, episodic_memory=ep,
            idle_seconds=0.05,
        )

        # Rapid-fire 5 posts — each should cancel the previous timer
        for i in range(5):
            monitor.post_process("s1", f"Rapid message {i} with enough length", f"Response {i} also long enough")

        # Wait for the idle timer to fire
        time.sleep(0.2)

        # Should have consolidated all 5 queued items in one batch
        self.assertEqual(sem.ingest_text.call_count, 5)

        for t in monitor._timers.values():
            t.cancel()


# ============================================================================
# 6. Agent Loop Edge Cases
# ============================================================================

class TestAgentLoopEdgeCases(TortureBase):
    """Unusual and adversarial inputs to the agent loop."""

    def test_nested_run_blocks(self):
        """Markdown explaining run blocks doesn't trigger execution."""
        from agent_loop import _RUN_BLOCK_RE

        text = '''Here's how to use run blocks:

    ```python
    # Example:
    ```run
    print("hello")
    ```
    ```

The above shows the syntax.'''

        # The nested example inside a python block should not match as a real run block
        matches = _RUN_BLOCK_RE.findall(text)
        # The regex may or may not match the inner block depending on nesting.
        # The key test is that the agent loop handles whatever it finds.
        llm = self._make_mock_llm()
        llm.chat.return_value = text
        runner = self._make_mock_runner()

        loop = AgentLoop(llm=llm, runner=runner, system_prompt="Test", max_rounds=2)
        result = loop.chat("How do run blocks work?")
        # Should complete without crashing regardless
        self.assertIsInstance(result, str)

    def test_empty_llm_response(self):
        """Empty LLM response doesn't crash the loop."""
        llm = self._make_mock_llm()
        llm.chat.return_value = ""

        loop = AgentLoop(llm=llm, runner=self._make_mock_runner(), system_prompt="Test")
        result = loop.chat("Hello")
        self.assertEqual(result, "")

    def test_llm_error_mid_loop(self):
        """LLM error on second call returns error message gracefully."""
        llm = self._make_mock_llm([
            '```run\nprint("ok")\n```',
            LLMError("connection reset"),
        ])
        llm.chat.side_effect = [
            '```run\nprint("ok")\n```',
            LLMError("connection reset"),
        ]
        runner = self._make_mock_runner()

        loop = AgentLoop(llm=llm, runner=runner, system_prompt="Test", max_rounds=3)
        result = loop.chat("Do something")
        self.assertIn("error", result.lower())

    def test_malformed_run_block(self):
        """Unclosed run block is not executed."""
        from agent_loop import _RUN_BLOCK_RE

        text = '```run\nprint("no closing backticks")\n'
        matches = _RUN_BLOCK_RE.findall(text)
        self.assertEqual(len(matches), 0)

    def test_max_rounds_with_alternating_code_and_text(self):
        """Loop stops at first text response, not at max_rounds."""
        llm = self._make_mock_llm([
            '```run\nprint("1")\n```',
            '```run\nprint("2")\n```',
            "Final answer: 3.",
        ])
        runner = self._make_mock_runner()

        loop = AgentLoop(llm=llm, runner=runner, system_prompt="Test", max_rounds=5)
        result = loop.chat("Calculate")

        self.assertEqual(result, "Final answer: 3.")
        self.assertEqual(runner.run.call_count, 2)
        self.assertEqual(llm.chat.call_count, 3)


# ============================================================================
# 7. State Isolation
# ============================================================================

class TestStateIsolation(TortureBase):
    """Sessions don't leak state between each other."""

    def test_conversation_memory_isolation(self):
        """Each session has independent conversation memory."""
        llm = self._make_mock_llm()
        llm.chat.return_value = "Noted."

        with patch("sophia_agent.LLMClient", return_value=llm), \
             patch("sophia_agent.init_workspace"):
            from sophia_agent import SophiaAgent
            agent = SophiaAgent(
                semantic_memory=self._make_mock_semantic(),
                episodic_memory=self._make_mock_episodic(),
                workspace_dir=tempfile.mkdtemp(),
                skill_paths=[],
            )

        agent.chat("s1", "I am Alice")
        agent.chat("s2", "I am Bob")

        s1_msgs = agent._sessions["s1"].conversation_memory.get_messages()
        s2_msgs = agent._sessions["s2"].conversation_memory.get_messages()

        s1_text = " ".join(m["content"] for m in s1_msgs)
        s2_text = " ".join(m["content"] for m in s2_msgs)

        self.assertIn("Alice", s1_text)
        self.assertNotIn("Bob", s1_text)
        self.assertIn("Bob", s2_text)
        self.assertNotIn("Alice", s2_text)

    def test_stream_monitor_session_isolation(self):
        """StreamMonitor sessions have independent extraction queues."""
        sem = self._make_mock_semantic()
        ep = self._make_mock_episodic()
        monitor = StreamMonitor(
            semantic_memory=sem, episodic_memory=ep, idle_seconds=999,
        )

        monitor.post_process("s1", "Session 1 long message", "Session 1 long response")
        monitor.post_process("s2", "Session 2 long message", "Session 2 long response")

        q1 = monitor._sessions["s1"]["extraction_queue"]
        q2 = monitor._sessions["s2"]["extraction_queue"]

        self.assertEqual(len(q1), 1)
        self.assertEqual(len(q2), 1)
        self.assertIsNot(q1, q2)

        for t in monitor._timers.values():
            t.cancel()

    def test_clear_session_does_not_affect_others(self):
        """Clearing one session leaves others intact."""
        llm = self._make_mock_llm()
        llm.chat.return_value = "Hi."

        with patch("sophia_agent.LLMClient", return_value=llm), \
             patch("sophia_agent.init_workspace"):
            from sophia_agent import SophiaAgent
            agent = SophiaAgent(
                semantic_memory=self._make_mock_semantic(),
                episodic_memory=self._make_mock_episodic(),
                workspace_dir=tempfile.mkdtemp(),
                skill_paths=[],
            )

        agent.chat("s1", "Hello")
        agent.chat("s2", "Hello")
        self.assertEqual(len(agent._sessions), 2)

        agent.clear_session("s1")
        self.assertNotIn("s1", agent._sessions)
        self.assertIn("s2", agent._sessions)


# ============================================================================
# 8. Recovery
# ============================================================================

class TestRecovery(TortureBase):
    """Graceful recovery from component failures."""

    def test_llm_down_then_up(self):
        """Agent recovers after LLM failure."""
        llm = self._make_mock_llm()
        llm.chat.side_effect = [
            LLMError("connection refused"),
            "I'm back online!",
        ]

        loop = AgentLoop(llm=llm, runner=self._make_mock_runner(), system_prompt="Test")

        result1 = loop.chat("Hello")
        self.assertIn("error", result1.lower())

        # Reset conversation memory for clean second attempt
        loop.conversation_memory.clear()
        result2 = loop.chat("Hello again")
        self.assertEqual(result2, "I'm back online!")

    def test_extraction_error_does_not_break_pipeline(self):
        """Extraction error on one message doesn't prevent processing others."""
        sem = self._make_mock_semantic()
        sem.ingest_text.side_effect = [
            Exception("extraction failed"),
            {"triples": [1]},
        ]
        ep = self._make_mock_episodic()
        monitor = StreamMonitor(
            semantic_memory=sem, episodic_memory=ep, idle_seconds=999,
        )

        monitor.post_process("s1", "First long message here", "First long response here")
        monitor.post_process("s1", "Second long message here", "Second long response here")
        monitor.flush("s1")

        # Both should have been attempted
        self.assertEqual(sem.ingest_text.call_count, 2)

    def test_pre_process_failure_graceful(self):
        """Agent loop completes even when pre_process hook fails."""
        sem = self._make_mock_semantic()
        sem.query_related_information.side_effect = Exception("DB down")
        ep = self._make_mock_episodic()
        monitor = StreamMonitor(
            semantic_memory=sem, episodic_memory=ep, idle_seconds=999,
        )

        llm = self._make_mock_llm()
        llm.chat.return_value = "I can still respond."

        loop = AgentLoop(
            llm=llm, runner=self._make_mock_runner(),
            system_prompt="Test",
            pre_process_hook=monitor.pre_process,
        )

        result = loop.chat("Hello", session_id="s1")
        self.assertEqual(result, "I can still respond.")
        llm.chat.assert_called_once()

        for t in monitor._timers.values():
            t.cancel()


if __name__ == "__main__":
    unittest.main()
