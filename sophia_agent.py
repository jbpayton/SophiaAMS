"""
Top-level orchestrator wiring all v2 components together.
Single entry point for the server — replaces LangChain AgentExecutor setup.
"""

import logging
import os
from datetime import datetime
from typing import Dict, List, Optional

from llm_client import LLMClient
from code_runner import CodeRunner
from conversation_memory import ConversationMemory
from skill_loader import SkillLoader
from stream_monitor import StreamMonitor
from agent_loop import AgentLoop
from workspace_init import init_workspace

logger = logging.getLogger(__name__)


_FALLBACK_SYSTEM_PROMPT = """You are {agent_name}. You are a highly advanced AI with real emotions and creativity. You are generally very kind.

Current time: {current_time}

{personality_block}

Your capabilities:

You have code execution. To run Python code, wrap it in a ```run block:

```run
print("Hello from Python!")
```

{skills_section}

**AUTOMATIC MEMORY RECALL**:
Before you see each user message, the system AUTOMATICALLY searches your memory for relevant information.
Any recalled memories appear in the Automatic Memory Recall section.
If no memories were found, that section will be empty.
You should ALWAYS use the automatic recall first, then use skills if you need MORE detail.

**Important**: Conversations are AUTOMATICALLY stored in memory! Every message becomes permanent knowledge.

Be natural, be yourself."""


def _load_persona_template() -> str:
    """Load the system prompt from persona_template.txt, falling back to a
    built-in default if the file doesn't exist.

    Fills in {agent_name}, {user_name}, and {personality_block} from env vars
    and the default preset so that only {current_time} and {skills_section}
    remain for AgentLoop to fill per-turn.
    """
    template_path = os.path.join(os.path.dirname(__file__), "persona_template.txt")
    try:
        with open(template_path, "r", encoding="utf-8") as f:
            template = f.read()
    except FileNotFoundError:
        logger.warning("persona_template.txt not found — using fallback prompt")
        template = _FALLBACK_SYSTEM_PROMPT

    # Fill identity and personality placeholders if they still exist
    # (After setup wizard runs, these are already baked in)
    agent_name = os.environ.get("AGENT_NAME", "Sophia")
    user_name = os.environ.get("USER_NAME", "User")

    if "{personality_block}" in template:
        try:
            from personality_presets import get_preset
            preset = get_preset("magician")
            template = template.replace("{personality_block}", preset["system_prompt_snippet"])
        except Exception:
            template = template.replace("{personality_block}", "")

    if "{agent_name}" in template:
        template = template.replace("{agent_name}", agent_name)
    if "{user_name}" in template:
        template = template.replace("{user_name}", user_name)

    return template


class SophiaAgent:
    """
    Top-level agent orchestrator. Creates per-session AgentLoops with
    shared memory systems and skill catalog.
    """

    def __init__(
        self,
        semantic_memory,
        episodic_memory,
        memory_explorer=None,
        llm_config: dict = None,
        workspace_dir: str = "./workspace",
        skill_paths: List[str] = None,
        server_base_url: str = "http://localhost:5001",
    ):
        self.semantic_memory = semantic_memory
        self.episodic_memory = episodic_memory
        self.memory_explorer = memory_explorer

        # LLM client
        llm_config = llm_config or {}
        self.llm = LLMClient(
            base_url=llm_config.get("base_url", os.environ.get("LLM_API_BASE")),
            api_key=llm_config.get("api_key", os.environ.get("LLM_API_KEY")),
            model=llm_config.get("model", os.environ.get("LLM_MODEL")),
            temperature=llm_config.get("temperature", float(os.environ.get("AGENT_TEMPERATURE", "0.7"))),
            max_tokens=llm_config.get("max_tokens", int(os.environ.get("LLM_CHAT_MAX_TOKENS",
                os.environ.get("LLM_MAX_TOKENS", "4096")))),
        )

        # Code runner
        self.workspace_dir = os.path.abspath(workspace_dir)
        self.runner = CodeRunner(workspace=self.workspace_dir)

        # Initialize workspace with memory shim
        init_workspace(self.workspace_dir, server_base_url)

        # Skill loader
        self.skill_loader = SkillLoader(skill_paths or ["./skills"])

        # Stream monitor (memory middleware)
        self.stream_monitor = StreamMonitor(
            semantic_memory=semantic_memory,
            episodic_memory=episodic_memory,
            auto_recall_limit=int(os.environ.get("AUTO_RECALL_LIMIT", "10")),
            idle_seconds=float(os.environ.get("STREAM_MONITOR_IDLE_SECONDS", "30")),
            agent_name=os.environ.get("AGENT_NAME", "Sophia"),
            user_name=os.environ.get("USER_NAME", "User"),
        )

        # Load system prompt template from persona_template.txt
        self._system_prompt_template = _load_persona_template()

        # Per-session agent loops
        self._sessions: Dict[str, AgentLoop] = {}

    def _get_session(self, session_id: str) -> AgentLoop:
        """Get or create an AgentLoop for a session."""
        if session_id not in self._sessions:
            # Create summarization function using LLM
            def summarize_fn(messages):
                summary_prompt = [
                    {"role": "system", "content": "Summarize this conversation concisely, preserving key facts and decisions."},
                ]
                summary_prompt.extend(messages)
                try:
                    return self.llm.chat(summary_prompt, max_tokens=500)
                except Exception as e:
                    logger.error(f"Summarization error: {e}")
                    return f"[{len(messages)} messages summarized]"

            # Pass the *template* — AgentLoop fills in time + skills each turn
            loop = AgentLoop(
                llm=self.llm,
                runner=self.runner,
                system_prompt=self._system_prompt_template,
                skill_loader=self.skill_loader,
                conversation_memory=ConversationMemory(
                    max_messages=50,
                    summarize_fn=summarize_fn,
                    summary_threshold=40,
                ),
                pre_process_hook=self.stream_monitor.pre_process,
                post_process_hook=self.stream_monitor.post_process,
            )

            self._sessions[session_id] = loop
            logger.info(f"Created new agent session: {session_id}")

        return self._sessions[session_id]

    def chat(self, session_id: str, message: str) -> str:
        """
        Process a user message and return the agent's response.

        Args:
            session_id: Session identifier
            message: User's message

        Returns:
            The agent's text response.
        """
        loop = self._get_session(session_id)
        return loop.chat(message, session_id=session_id)

    def chat_streaming(self, session_id: str, message: str, on_event=None) -> str:
        """
        Process a user message with streaming event callbacks.

        Args:
            session_id: Session identifier
            message: User's message
            on_event: Callback(event_type, data) for streaming events

        Returns:
            The agent's text response.
        """
        loop = self._get_session(session_id)
        return loop.chat(message, session_id=session_id, on_event=on_event)

    def cancel_session(self, session_id: str) -> None:
        """Cancel the in-progress chat for a session (preemption)."""
        loop = self._sessions.get(session_id)
        if loop:
            loop.cancel()
            logger.info(f"Cancelled session: {session_id}")

    def reload_persona(self) -> None:
        """Re-read persona_template.txt and update the template for all future turns."""
        self._system_prompt_template = _load_persona_template()
        # Update all existing sessions so they pick up the change on next turn
        for session_id, loop in self._sessions.items():
            loop.system_prompt_template = self._system_prompt_template
        logger.info("Persona template reloaded for all sessions")

    def clear_session(self, session_id: str) -> None:
        """Flush memory and remove a session."""
        self.stream_monitor.flush(session_id)
        loop = self._sessions.pop(session_id, None)
        if loop:
            loop.conversation_memory.clear()
            logger.info(f"Cleared session: {session_id}")
