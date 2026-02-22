"""
Core agent loop replacing LangChain's AgentExecutor.
LLM call -> parse ```run``` blocks -> execute -> feedback, up to max_rounds.
"""

import re
import logging
from datetime import datetime
from typing import Callable, Dict, List, Optional

from llm_client import LLMClient
from code_runner import CodeRunner
from conversation_memory import ConversationMemory
from skill_loader import SkillLoader

logger = logging.getLogger(__name__)

# Pattern to match ```run ... ``` code blocks
_RUN_BLOCK_RE = re.compile(r"```run\s*\n(.*?)```", re.DOTALL)


class AgentLoop:
    """
    Minimal agent loop: send messages to LLM, detect ```run``` code blocks,
    execute them, feed results back, repeat until no more code blocks or
    max rounds reached.
    """

    def __init__(
        self,
        llm: LLMClient,
        runner: CodeRunner,
        system_prompt: str,
        skill_loader: SkillLoader = None,
        conversation_memory: ConversationMemory = None,
        pre_process_hook: Callable[[str, str], str] = None,
        post_process_hook: Callable[[str, str, str], None] = None,
        max_rounds: int = 5,
    ):
        self.llm = llm
        self.runner = runner
        self.system_prompt_template = system_prompt
        self.skill_loader = skill_loader
        self.conversation_memory = conversation_memory or ConversationMemory()
        self.pre_process_hook = pre_process_hook
        self.post_process_hook = post_process_hook
        self.max_rounds = max_rounds

    def chat(self, user_input: str, session_id: str = "default") -> str:
        """
        Process a user message through the agent loop.

        1. Run pre_process_hook (e.g., memory recall)
        2. Add user message to conversation
        3. Loop: LLM call -> parse run blocks -> execute -> feed results
        4. Run post_process_hook (e.g., save to memory)
        5. Return final text response

        Args:
            user_input: The user's message
            session_id: Session identifier for hooks

        Returns:
            The agent's final text response.
        """
        # Pre-process hook (memory recall)
        context = ""
        if self.pre_process_hook:
            try:
                context = self.pre_process_hook(user_input, session_id)
            except Exception as e:
                logger.error(f"Pre-process hook error: {e}")

        # Add user message to conversation memory
        self.conversation_memory.add_message("user", user_input)

        # Summarize if needed
        if self.conversation_memory.needs_summarization():
            self.conversation_memory.summarize()

        # Agent loop
        final_response = ""
        for round_num in range(self.max_rounds):
            messages = self._build_messages(context)

            try:
                response = self.llm.chat(messages)
            except Exception as e:
                logger.error(f"LLM error in round {round_num}: {e}")
                final_response = f"I encountered an error: {e}"
                break

            # Check for run blocks
            run_blocks = self._extract_run_blocks(response)

            if not run_blocks:
                # No code to execute — this is the final answer
                final_response = response
                break

            # Execute code blocks and collect results
            execution_results = []
            for i, code in enumerate(run_blocks):
                result = self.runner.run(code)
                execution_results.append(f"[Execution {i + 1}]\n{result.summary()}")

            # Add assistant response + execution feedback to conversation
            self.conversation_memory.add_message("assistant", response)
            feedback = "\n\n".join(execution_results)
            self.conversation_memory.add_message("system", f"Code execution results:\n{feedback}")
            context = ""  # Don't re-inject recall context in subsequent rounds
        else:
            # Max rounds reached — use last response
            final_response = response if 'response' in dir() else "I reached the maximum number of action rounds."

        # Record the final response in conversation
        self.conversation_memory.add_message("assistant", final_response)

        # Post-process hook (memory save)
        if self.post_process_hook:
            try:
                self.post_process_hook(session_id, user_input, final_response)
            except Exception as e:
                logger.error(f"Post-process hook error: {e}")

        return final_response

    def _extract_run_blocks(self, text: str) -> List[str]:
        """Extract code from ```run ... ``` blocks."""
        return _RUN_BLOCK_RE.findall(text)

    def _build_system_prompt(self) -> str:
        """
        Format the system prompt template with live data:
        - Current time (refreshed every turn)
        - Skills catalog (refreshed every turn so new skills are picked up)
        """
        # Refresh skill catalog to pick up any newly created skills
        skills_text = "No skills available."
        if self.skill_loader:
            self.skill_loader.refresh()
            skills_text = self.skill_loader.descriptions()

        try:
            return self.system_prompt_template.format(
                current_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                skills_section=skills_text,
            )
        except KeyError:
            # Template doesn't have placeholders — use as-is
            return self.system_prompt_template

    def _build_messages(self, context: str = "") -> List[Dict]:
        """
        Build the full message list for the LLM:
        system prompt (with live time + skills) + recall context + conversation.
        """
        messages = []

        # System prompt — rebuilt every turn for fresh time + skills
        messages.append({"role": "system", "content": self._build_system_prompt()})

        # Recall context — separate system message so the LLM can distinguish
        # stable instructions from per-turn memory context.
        if context:
            messages.append({
                "role": "system",
                "content": f"Automatic Memory Recall:\n{context}",
            })

        # Conversation history
        messages.extend(self.conversation_memory.get_messages())

        return messages
