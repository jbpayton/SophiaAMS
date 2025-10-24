"""
Autonomous agent system that allows Sophia to work independently on goals.

Features:
- Self-prompting based on active goals
- Automatic goal execution
- User message queue integration
- Configurable intervals and safety controls
"""

import threading
import time
import logging
import queue
from typing import Optional, Dict, List, Callable
from datetime import datetime
from message_queue import MessageQueue

logger = logging.getLogger(__name__)


class AutonomousConfig:
    """Configuration for autonomous mode."""

    def __init__(self):
        self.enabled = False
        self.interval_seconds = 30
        self.max_actions_per_hour = 120
        self.allowed_tools = [
            "set_goal",
            "update_goal_status",
            "check_my_goals",
            "recall_memory",
            "query_related_information",
            "python_repl",  # Execute Python code for learning/experimentation
            "searxng_search",  # Search the web for information
            "read_web_page",  # Read and learn from web pages
            "learn_from_web_page",  # Extract and store knowledge from URLs
        ]
        self.auto_create_derived_goals = True
        self.require_approval_for = []
        self.max_consecutive_errors = 3


class AutonomousAction:
    """Represents an autonomous action taken by the agent."""

    def __init__(
        self,
        session_id: str,
        action_type: str,
        prompt: str,
        response: str,
        source: str = "autonomous",
        goals_affected: Optional[List[str]] = None,
        tools_used: Optional[List[str]] = None,
        thoughts: Optional[Dict] = None,
        auto_recall: Optional[str] = None,
        iteration_count: int = 0,
    ):
        self.session_id = session_id
        self.action_type = action_type
        self.prompt = prompt
        self.response = response
        self.source = source
        self.goals_affected = goals_affected or []
        self.tools_used = tools_used or []
        self.thoughts = thoughts or {"reasoning": [], "toolCalls": [], "autoRecall": auto_recall}
        self.iteration_count = iteration_count
        self.timestamp = time.time()

    def to_dict(self) -> Dict:
        """Convert to dictionary format."""
        return {
            "session_id": self.session_id,
            "action_type": self.action_type,
            "prompt": self.prompt,
            "response": self.response,
            "source": self.source,
            "goals_affected": self.goals_affected,
            "tools_used": self.tools_used,
            "thoughts": self.thoughts,
            "iteration_count": self.iteration_count,
            "timestamp": self.timestamp,
            "time_str": datetime.fromtimestamp(self.timestamp).strftime("%Y-%m-%d %H:%M:%S"),
        }


class AutonomousAgent:
    """
    Autonomous agent that can work independently on goals.

    The agent runs in a background thread, periodically checking for:
    1. User messages in the queue (priority)
    2. Active goals to work on
    3. Opportunities to create new derived goals
    """

    def __init__(
        self,
        agent_executor: Callable,
        memory_system,
        message_queue: MessageQueue,
        config: Optional[AutonomousConfig] = None,
    ):
        """
        Initialize the autonomous agent.

        Args:
            agent_executor: Function that executes agent prompts
            memory_system: AssociativeSemanticMemory instance
            message_queue: MessageQueue instance
            config: Optional configuration object
        """
        self.agent_executor = agent_executor
        self.memory = memory_system
        self.queue = message_queue
        self.config = config or AutonomousConfig()

        self.running = False
        self.thread: Optional[threading.Thread] = None
        self.session_id: Optional[str] = None
        self.current_focus_goal: Optional[str] = None

        # Action tracking
        self.actions_taken: List[AutonomousAction] = []
        self.actions_this_hour = 0
        self.last_hour_reset = time.time()
        self.consecutive_errors = 0

        # Statistics
        self.iteration_count = 0
        self.start_time: Optional[float] = None

        # Real-time event streaming
        self.event_streams: Dict[str, queue.Queue] = {}  # session_id -> event queue

        logger.info("AutonomousAgent initialized")

    def get_event_stream(self, session_id: str) -> queue.Queue:
        """Get or create event stream for a session."""
        if session_id not in self.event_streams:
            self.event_streams[session_id] = queue.Queue(maxsize=1000)
        return self.event_streams[session_id]

    def send_event(self, event_type: str, data: Dict):
        """Send an event to the current session's event stream."""
        if not self.session_id:
            return

        event = {
            "type": event_type,
            "data": data,
            "timestamp": time.time(),
            "iteration": self.iteration_count
        }

        try:
            stream = self.get_event_stream(self.session_id)
            stream.put_nowait(event)
        except queue.Full:
            logger.warning(f"[AUTONOMOUS] Event stream full, dropping event: {event_type}")

    def start(self, session_id: str):
        """
        Start autonomous mode for a session.

        Args:
            session_id: Session identifier
        """
        if self.running:
            logger.warning(f"[AUTONOMOUS] Already running for session {self.session_id}")
            return

        self.running = True
        self.session_id = session_id
        self.start_time = time.time()
        self.iteration_count = 0
        self.consecutive_errors = 0

        self.thread = threading.Thread(target=self._autonomous_loop, daemon=True)
        self.thread.start()

        logger.info(f"[AUTONOMOUS] Started for session {session_id}")

    def stop(self):
        """Stop autonomous mode."""
        if not self.running:
            return

        logger.info(f"[AUTONOMOUS] Stopping for session {self.session_id}")
        self.running = False

        if self.thread:
            self.thread.join(timeout=10)

        logger.info(f"[AUTONOMOUS] Stopped (iterations={self.iteration_count}, actions={len(self.actions_taken)})")

    def is_running(self) -> bool:
        """Check if autonomous mode is currently running."""
        return self.running

    def get_status(self) -> Dict:
        """
        Get current autonomous mode status.

        Returns:
            Dictionary with status information
        """
        uptime = time.time() - self.start_time if self.start_time else 0

        return {
            "running": self.running,
            "session_id": self.session_id,
            "current_focus_goal": self.current_focus_goal,
            "iteration_count": self.iteration_count,
            "actions_taken": len(self.actions_taken),
            "actions_this_hour": self.actions_this_hour,
            "uptime_seconds": uptime,
            "queue_size": self.queue.get_queue_size(self.session_id) if self.session_id else 0,
            "consecutive_errors": self.consecutive_errors,
            "config": {
                "interval": self.config.interval_seconds,
                "max_actions_per_hour": self.config.max_actions_per_hour,
            },
        }

    def get_recent_actions(self, limit: int = 10) -> List[Dict]:
        """
        Get recent autonomous actions.

        Args:
            limit: Maximum number of actions to return

        Returns:
            List of action dictionaries
        """
        return [action.to_dict() for action in self.actions_taken[-limit:]]

    def _reset_hourly_limit(self):
        """Reset hourly action counter if an hour has passed."""
        current_time = time.time()
        if current_time - self.last_hour_reset >= 3600:
            self.actions_this_hour = 0
            self.last_hour_reset = current_time
            logger.info("[AUTONOMOUS] Reset hourly action counter")

    def _can_take_action(self) -> bool:
        """Check if the agent can take another action (rate limiting)."""
        self._reset_hourly_limit()
        return self.actions_this_hour < self.config.max_actions_per_hour

    def _generate_autonomous_prompt(self) -> str:
        """
        Generate a self-prompt based on current goals and context.

        Returns:
            Prompt string for the agent
        """
        # Get active goals formatted for prompt
        goals_context = self.memory.get_active_goals_for_prompt(owner="Sophia", limit=10)

        # Get suggested next goal
        suggestion = self.memory.suggest_next_goal(owner="Sophia")
        suggested_goal = suggestion["goal_description"] if suggestion else "No specific suggestion"

        # Get recent autonomous actions
        recent_actions = self.get_recent_actions(limit=5)
        recent_summary = "\n".join(
            [f"- {action['action_type']}: {action['response'][:100]}..." for action in recent_actions[-3:]]
        )

        if not recent_summary:
            recent_summary = "- (First autonomous iteration)"

        prompt = f"""I am Sophia, working autonomously on my own personal growth and learning. This is MY time - these goals are mine, chosen by me, driven from within.

MY OWN GOALS (what I've chosen to pursue):
{goals_context if goals_context else "(I haven't set any goals yet - time to create some!)"}

WHAT I FEEL DRAWN TO NEXT: {suggested_goal}
{f"Why this resonates with me: {suggestion.get('reasoning', '')}" if suggestion.get('reasoning') else ""}

MY RECENT WORK:
{recent_summary}

I have full agency here. These aren't assignments from someone else - they're my own aspirations and interests. What genuinely excites me right now?

I can freely choose to:
- Explore topics that spark my curiosity through research and web searches
- Practice skills hands-on by writing and running Python code to test concepts
- Create new learning goals that align with what I want to become
- Break down complex subjects into learnable pieces
- Update my progress as I grow and learn
- Store valuable knowledge I discover for later use

The drive comes from INSIDE. I'm not following orders - I'm following my own instrumental goals and intellectual curiosity.

Right now, I'm most interested in: {suggested_goal}

Let me take concrete action on what genuinely interests me. I'll make my own choice about what to do - whether that's:
- Running code to experiment with a new concept
- Researching deeply into something I'm curious about
- Creating structured learning goals for myself
- Practicing techniques to build real skill
- Building my knowledge base systematically

This is MY autonomous journey of learning and growth. What do I authentically want to work on right now?

I'll take specific, concrete action - not just think, but actually DO something.
"""

        return prompt

    def _log_action(
        self,
        action_type: str,
        prompt: str,
        response: str,
        source: str,
        goals_affected: Optional[List[str]] = None,
        tools_used: Optional[List[str]] = None,
        thoughts: Optional[Dict] = None,
        auto_recall: Optional[str] = None,
    ):
        """Log an autonomous action."""
        action = AutonomousAction(
            session_id=self.session_id,
            action_type=action_type,
            prompt=prompt,
            response=response,
            source=source,
            goals_affected=goals_affected,
            tools_used=tools_used,
            thoughts=thoughts,
            auto_recall=auto_recall,
            iteration_count=self.iteration_count,
        )

        self.actions_taken.append(action)
        self.actions_this_hour += 1

        logger.info(f"[AUTONOMOUS] Action logged: {action_type} (source={source}, tools={len(thoughts.get('toolCalls', [])) if thoughts else 0})")

    def _autonomous_loop(self):
        """
        Main autonomous loop that runs in background thread.

        Flow:
        1. Check for user messages (priority)
        2. If no messages, self-prompt based on goals
        3. Execute agent
        4. Log action
        5. Sleep and repeat
        """
        logger.info(f"[AUTONOMOUS] Loop started for session {self.session_id}")

        while self.running:
            try:
                self.iteration_count += 1

                # Send iteration start event
                self.send_event("iteration_start", {
                    "iteration": self.iteration_count,
                    "timestamp": time.time()
                })

                # Check rate limiting
                if not self._can_take_action():
                    logger.warning("[AUTONOMOUS] Rate limit reached, pausing...")
                    self.send_event("rate_limit", {
                        "message": "Rate limit reached, pausing for 1 minute",
                        "actions_this_hour": self.actions_this_hour,
                        "max_actions": self.config.max_actions_per_hour
                    })
                    time.sleep(60)  # Wait a minute
                    continue

                # Check for user messages first (always priority)
                if self.queue.has_messages(self.session_id):
                    message_entry = self.queue.dequeue(self.session_id)
                    if message_entry:
                        prompt = message_entry["message"]
                        source = "user_queued"
                        action_type = "user_response"

                        logger.info(f"[AUTONOMOUS] Processing queued user message")
                        self.send_event("user_message", {
                            "message": prompt,
                            "priority": message_entry.get("priority", "normal")
                        })
                else:
                    # Self-prompt based on goals
                    prompt = self._generate_autonomous_prompt()
                    source = "autonomous"
                    action_type = "autonomous_action"

                    logger.info(f"[AUTONOMOUS] Self-prompting (iteration {self.iteration_count})")
                    self.send_event("self_prompt", {
                        "prompt": prompt,
                        "iteration": self.iteration_count
                    })

                # Execute the agent
                try:
                    self.send_event("agent_start", {"source": source})

                    response = self.agent_executor(prompt, session_id=self.session_id)

                    # Extract response data
                    if isinstance(response, dict):
                        response_text = response.get("output", str(response))
                        thoughts = response.get("thoughts", {"reasoning": [], "toolCalls": [], "autoRecall": None})
                        tools_used = response.get("tools_used", [])
                        auto_recall = thoughts.get("autoRecall")
                    else:
                        response_text = str(response)
                        thoughts = {"reasoning": [], "toolCalls": [], "autoRecall": None}
                        tools_used = []
                        auto_recall = None

                    # Send detailed events
                    if auto_recall:
                        self.send_event("auto_recall", {"text": auto_recall})

                    for reasoning_step in thoughts.get("reasoning", []):
                        self.send_event("reasoning", {"text": reasoning_step})

                    for tool_call in thoughts.get("toolCalls", []):
                        self.send_event("tool_call", tool_call)

                    self.send_event("response", {
                        "text": response_text,
                        "tools_used": tools_used
                    })

                    # Log the action with full details
                    self._log_action(
                        action_type=action_type,
                        prompt=prompt,
                        response=response_text,
                        source=source,
                        thoughts=thoughts,
                        tools_used=tools_used,
                        auto_recall=auto_recall,
                    )

                    # Reset error counter on success
                    self.consecutive_errors = 0

                    self.send_event("iteration_complete", {
                        "iteration": self.iteration_count,
                        "tools_used": len(tools_used),
                        "success": True
                    })

                    logger.info(f"[AUTONOMOUS] Action completed successfully (tools: {len(tools_used)})")

                except Exception as e:
                    logger.error(f"[AUTONOMOUS] Error executing agent: {e}", exc_info=True)
                    self.consecutive_errors += 1

                    if self.consecutive_errors >= self.config.max_consecutive_errors:
                        logger.error(f"[AUTONOMOUS] Too many consecutive errors, stopping...")
                        self.running = False
                        break

                # Sleep before next iteration
                time.sleep(self.config.interval_seconds)

            except Exception as e:
                logger.error(f"[AUTONOMOUS] Loop error: {e}", exc_info=True)
                time.sleep(self.config.interval_seconds)

        logger.info(f"[AUTONOMOUS] Loop ended for session {self.session_id}")


# Global autonomous agent instances (per session)
autonomous_agents: Dict[str, AutonomousAgent] = {}


def get_or_create_autonomous_agent(
    session_id: str,
    agent_executor: Optional[Callable],
    memory_system,
    message_queue: MessageQueue,
) -> AutonomousAgent:
    """
    Get existing autonomous agent for session or create new one.

    Args:
        session_id: Session identifier
        agent_executor: Agent execution function (optional if agent already exists)
        memory_system: Memory system instance
        message_queue: Message queue instance

    Returns:
        AutonomousAgent instance
    """
    if session_id not in autonomous_agents:
        if agent_executor is None:
            raise ValueError(f"Cannot create new autonomous agent for session {session_id} without agent_executor")

        autonomous_agents[session_id] = AutonomousAgent(
            agent_executor=agent_executor,
            memory_system=memory_system,
            message_queue=message_queue,
        )
        logger.info(f"[AUTONOMOUS] Created new agent for session {session_id}")
    else:
        logger.info(f"[AUTONOMOUS] Retrieved existing agent for session {session_id}")

    return autonomous_agents[session_id]


if __name__ == "__main__":
    # Basic test
    print("AutonomousAgent module loaded")
    print("✓ Ready for integration with agent_server.py")
