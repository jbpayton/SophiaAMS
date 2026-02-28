"""
Core agent loop replacing LangChain's AgentExecutor.
LLM call -> parse ```run``` blocks -> execute -> feedback, up to max_rounds.
"""

import re
import logging
import threading
from datetime import datetime
from typing import Callable, Dict, List, Optional

from llm_client import LLMClient
from code_runner import CodeRunner
from conversation_memory import ConversationMemory
from skill_loader import SkillLoader

logger = logging.getLogger(__name__)

# Pattern to match ```run ... ``` code blocks
_RUN_BLOCK_RE = re.compile(r"```run\s*\n(.*?)```", re.DOTALL)

# Pattern to extract <think>...</think> blocks before LLMClient strips them
_THINK_RE = re.compile(r'<think>(.*?)</think>', re.DOTALL)

# Plaintext thinking detection (Qwen3.5 style)
_PLAINTEXT_THINK_HEADER_RE = re.compile(
    r'^(?:Thinking Process|Internal Reasoning|Reasoning|Thought Process)\s*:\s*\n',
    re.MULTILINE
)


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

        # Cancellation support (Feature 3: Preemption)
        self._cancel = threading.Event()

    def cancel(self):
        """Signal the current chat() call to cancel."""
        self._cancel.set()

    def reset_cancel(self):
        """Clear the cancellation flag."""
        self._cancel.clear()

    def _emit(self, on_event, event_type: str, data: dict):
        """Safely emit a streaming event if callback is provided."""
        if on_event:
            try:
                on_event(event_type, data)
            except Exception as e:
                logger.error(f"on_event callback error: {e}")

    def chat(self, user_input: str, session_id: str = "default", on_event: Callable = None) -> str:
        """
        Process a user message through the agent loop.

        Args:
            user_input: The user's message
            session_id: Session identifier for hooks
            on_event: Optional callback(event_type, data) for streaming events.
                      Event types: auto_recall, thinking, reasoning, tool_start,
                      tool_end, tool_error, final_response

        Returns:
            The agent's final text response.
        """
        self.reset_cancel()

        # Pre-process hook (memory recall)
        context = ""
        if self.pre_process_hook:
            try:
                context = self.pre_process_hook(user_input, session_id)
            except Exception as e:
                logger.error(f"Pre-process hook error: {e}")

        # Emit auto_recall event with memory context
        if context:
            self._emit(on_event, "auto_recall", {"memories": context})

        # Add user message to conversation memory
        self.conversation_memory.add_message("user", user_input)

        # Summarize if needed
        if self.conversation_memory.needs_summarization():
            self.conversation_memory.summarize()

        # Agent loop
        final_response = ""
        for round_num in range(self.max_rounds):
            # Check cancellation before LLM call
            if self._cancel.is_set():
                final_response = "[Paused to handle your message — I'll continue this later]"
                break

            messages = self._build_messages(context)

            # Estimate input token count and log it
            input_chars = sum(len(m.get("content", "")) for m in messages)
            input_tokens_est = input_chars // 4  # rough estimate
            logger.info(f"Round {round_num+1}: sending {len(messages)} messages, ~{input_chars} chars (~{input_tokens_est} tokens est)")

            self._emit(on_event, "thinking", {"round": round_num + 1})

            try:
                # Always get raw response (with think tokens) so we can
                # extract ```run blocks that models sometimes put inside
                # <think> tags. We strip think tokens ourselves below.
                if hasattr(self.llm, 'strip_thinking'):
                    original_strip = self.llm.strip_thinking
                    self.llm.strip_thinking = False
                    response = self.llm.chat(messages)
                    self.llm.strip_thinking = original_strip
                else:
                    response = self.llm.chat(messages)
            except Exception as e:
                logger.error(f"LLM error in round {round_num}: {e}")
                final_response = f"I encountered an error: {e}"
                self._emit(on_event, "error", {"message": str(e)})
                break

            # Log raw response for debugging
            raw_len = len(response)
            has_think = '<think>' in response or '</think>' in response
            has_plaintext_think = bool(_PLAINTEXT_THINK_HEADER_RE.search(response))
            has_run = '```run' in response
            finish_reason = getattr(self.llm, '_last_finish_reason', 'unknown')
            logger.info(
                f"Round {round_num+1}: raw response {raw_len} chars, "
                f"has_think={has_think}, has_plaintext_think={has_plaintext_think}, "
                f"has_run={has_run}, finish_reason={finish_reason}"
            )
            if raw_len < 500:
                logger.info(f"Round {round_num+1} full response: {response!r}")
            else:
                logger.info(f"Round {round_num+1} response preview: {response[:200]!r} ... {response[-200:]!r}")

            # Extract run blocks BEFORE stripping think tokens, because
            # some models put ```run blocks inside <think> tags.
            run_blocks = self._extract_run_blocks(response)
            logger.info(f"Round {round_num+1}: found {len(run_blocks)} run blocks")

            # Emit reasoning blocks if streaming
            if on_event:
                think_blocks = _THINK_RE.findall(response)
                for think_content in think_blocks:
                    think_text = think_content.strip()
                    if think_text:
                        self._emit(on_event, "reasoning", {"text": think_text})

                # Also emit plaintext thinking as reasoning events
                if has_plaintext_think:
                    match = _PLAINTEXT_THINK_HEADER_RE.search(response)
                    if match:
                        think_start = match.start()
                        think_text = response[think_start:]
                        # Try to find where thinking ends (before code fence or uppercase line after blank)
                        end_match = re.search(r'\n(?:```|[A-Z])', think_text[match.end() - think_start:])
                        if end_match:
                            think_text = think_text[:match.end() - think_start + end_match.start()]
                        self._emit(on_event, "reasoning", {"text": think_text.strip()})

            # Strip think tokens from the response text
            response = LLMClient._strip_think_tokens(response)
            stripped_len = len(response)
            logger.info(f"Round {round_num+1}: after strip_think {stripped_len} chars (removed {raw_len - stripped_len})")
            if stripped_len < 300 and stripped_len > 0:
                logger.info(f"Round {round_num+1} stripped response: {response!r}")

            # Detect truncated response: model spent all tokens on thinking
            if not response.strip() and not run_blocks:
                logger.warning(f"Round {round_num+1}: empty after stripping think tokens (finish_reason={finish_reason})")
                # Retry with an explicit "no thinking" nudge
                messages.append({
                    "role": "assistant",
                    "content": "(I was thinking about this but ran out of space. Let me respond directly.)"
                })
                messages.append({
                    "role": "user",
                    "content": "Please respond directly without extensive internal reasoning. What were you going to say?"
                })
                try:
                    retry_response = self.llm.chat(messages) if not hasattr(self.llm, 'strip_thinking') else self._retry_direct(messages)
                    retry_response = LLMClient._strip_think_tokens(retry_response)
                    if retry_response.strip():
                        logger.info(f"Round {round_num+1}: retry succeeded with {len(retry_response)} chars")
                        response = retry_response
                    else:
                        logger.warning(f"Round {round_num+1}: retry also empty, using fallback")
                        response = "I was thinking about your request but couldn't formulate a complete response. Could you try rephrasing or simplifying your question?"
                except Exception as e:
                    logger.error(f"Round {round_num+1}: retry failed: {e}")
                    response = "I was thinking about your request but couldn't formulate a complete response. Could you try rephrasing or simplifying your question?"

            # Check cancellation between rounds
            if self._cancel.is_set():
                final_response = "[Paused to handle your message — I'll continue this later]"
                break

            if not run_blocks:
                # No code to execute — this is the final answer
                final_response = response
                break

            # Cap run blocks per round to prevent the model from speed-running
            # entire workflows in a single response without seeing real results.
            max_blocks = 2
            if len(run_blocks) > max_blocks:
                logger.info(f"Round {round_num+1}: capping {len(run_blocks)} run blocks to {max_blocks}")
                run_blocks = run_blocks[:max_blocks]

            # Execute code blocks and collect results
            execution_results = []
            for i, code in enumerate(run_blocks):
                self._emit(on_event, "tool_start", {"tool": "code_execution", "input": code})

                try:
                    result = self.runner.run(code)
                    result_text = result.summary()
                    execution_results.append(f"[Execution {i + 1}]\n{result_text}")
                    self._emit(on_event, "tool_end", {"output": result_text})
                except Exception as e:
                    error_text = str(e)
                    execution_results.append(f"[Execution {i + 1}]\nError: {error_text}")
                    self._emit(on_event, "tool_error", {"error": error_text})

            # Add assistant response + execution feedback to conversation.
            # Include the code blocks in the assistant message so the model
            # knows what was executed (think-stripped response may be just text).
            assistant_msg = response
            if run_blocks and '```run' not in response:
                # The visible response lost the code blocks during think-stripping;
                # re-attach them so the model has context for what was executed.
                code_section = "\n".join(f"```run\n{code}\n```" for code in run_blocks)
                assistant_msg = f"{response}\n{code_section}" if response.strip() else code_section
            self.conversation_memory.add_message("assistant", assistant_msg)
            feedback = "\n\n".join(execution_results)
            self.conversation_memory.add_message("user", f"[Code execution results]\n{feedback}\n\nNow respond to the user based on these results. Use ```run blocks if you need to take more actions.")
            context = ""  # Don't re-inject recall context in subsequent rounds
        else:
            # Max rounds reached — use last response
            final_response = response if 'response' in dir() else "I reached the maximum number of action rounds."

        # Record the final response in conversation
        self.conversation_memory.add_message("assistant", final_response)

        # Emit final response
        self._emit(on_event, "final_response", {"response": final_response})

        # Post-process hook (memory save)
        if self.post_process_hook:
            try:
                self.post_process_hook(session_id, user_input, final_response)
            except Exception as e:
                logger.error(f"Post-process hook error: {e}")

        return final_response

    def _retry_direct(self, messages: list) -> str:
        """Retry LLM call with strip_thinking disabled so we get raw output."""
        original_strip = self.llm.strip_thinking
        self.llm.strip_thinking = False
        try:
            return self.llm.chat(messages)
        finally:
            self.llm.strip_thinking = original_strip

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
        system prompt (with live time + skills + recall context) + conversation.

        Note: Some models (e.g. Qwen3.5) reject multiple system messages,
        so we merge the recall context into the main system prompt.
        """
        messages = []

        # System prompt — rebuilt every turn for fresh time + skills
        system_content = self._build_system_prompt()

        # Merge recall context into the system prompt (some model templates
        # reject multiple system messages)
        if context:
            system_content += f"\n\n--- Automatic Memory Recall ---\n{context}"

        messages.append({"role": "system", "content": system_content})

        # Conversation history
        messages.extend(self.conversation_memory.get_messages())

        return messages
