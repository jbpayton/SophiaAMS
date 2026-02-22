"""
SophiaAMS v2 — Event-Driven Entry Point

Bootstraps memory systems, SophiaAgent, EventBus, adapters, and
EventProcessor, then runs uvicorn + the event loop together.

On first run (no .setup_complete sentinel), launches a setup wizard
instead of the full application.
"""

import asyncio
import atexit
import logging
import os
import re
import signal
import subprocess
import sys
import webbrowser
from typing import Any, Dict

import yaml
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
SETUP_SENTINEL = os.path.join(ROOT_DIR, ".setup_complete")
FRONTEND_DIR = os.path.join(ROOT_DIR, "sophia-web")

# ---------------------------------------------------------------------------
# Config loader
# ---------------------------------------------------------------------------

def _expand_env_vars(value: Any) -> Any:
    """Recursively expand ${VAR} references in config values."""
    if isinstance(value, str):
        return re.sub(
            r"\$\{(\w+)\}",
            lambda m: os.environ.get(m.group(1), m.group(0)),
            value,
        )
    if isinstance(value, dict):
        return {k: _expand_env_vars(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_expand_env_vars(v) for v in value]
    return value


def load_config(path: str = None) -> Dict:
    """Load and return the sophia_config.yaml as a dict."""
    path = path or os.environ.get(
        "SOPHIA_CONFIG_PATH",
        os.path.join(os.path.dirname(__file__), "sophia_config.yaml"),
    )
    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    return _expand_env_vars(raw)


# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------

async def build_and_run() -> None:
    """Wire everything together and run."""

    config = load_config()
    sources_cfg = config.get("event_sources", {})
    agent_cfg = config.get("agent", {})

    # ------------------------------------------------------------------
    # 1. Memory systems (same as agent_server.py)
    # ------------------------------------------------------------------
    from AssociativeSemanticMemory import AssociativeSemanticMemory
    from VectorKnowledgeGraph import VectorKnowledgeGraph
    from EpisodicMemory import EpisodicMemory
    from MemoryExplorer import MemoryExplorer

    logger.info("Initializing memory systems...")
    kgraph = VectorKnowledgeGraph()
    memory_system = AssociativeSemanticMemory(kgraph)
    episodic_memory = EpisodicMemory()
    memory_explorer = MemoryExplorer(kgraph)
    logger.info("Memory systems initialized (semantic + episodic + explorer)")

    # ------------------------------------------------------------------
    # 2. SophiaAgent
    # ------------------------------------------------------------------
    from sophia_agent import SophiaAgent

    port = int(os.getenv("AGENT_PORT", "5001"))

    sophia = SophiaAgent(
        semantic_memory=memory_system,
        episodic_memory=episodic_memory,
        memory_explorer=memory_explorer,
        workspace_dir=os.environ.get("WORKSPACE_PATH", "./workspace"),
        skill_paths=[os.environ.get("SKILLS_PATH", "./skills")],
        server_base_url=f"http://localhost:{port}",
    )

    # ------------------------------------------------------------------
    # 3. EventBus + EventProcessor
    # ------------------------------------------------------------------
    from event_bus import EventBus
    from event_processor import EventProcessor

    bus = EventBus()
    bus.bind_loop(asyncio.get_running_loop())

    processor = EventProcessor(
        bus=bus,
        sophia_chat=sophia.chat,
        memory_system=memory_system,
        rate_limit_per_hour=agent_cfg.get("rate_limit_per_hour", 120),
    )

    # ------------------------------------------------------------------
    # 4. Adapters
    # ------------------------------------------------------------------
    adapters = []

    # WebUI adapter — always on (needed by agent_server.py routes)
    from adapters.webui_adapter import WebUIAdapter
    webui_adapter = WebUIAdapter(bus)
    processor.register_response_handler("webui", webui_adapter.handle_response)
    adapters.append(webui_adapter)

    # Scheduler adapter
    sched_cfg = sources_cfg.get("scheduler", {})
    if sched_cfg.get("enabled", False):
        from adapters.scheduler_adapter import SchedulerAdapter
        scheduler = SchedulerAdapter(bus, jobs=sched_cfg.get("jobs", []))
        adapters.append(scheduler)

    # Goal engine adapter — drives the continuous loop
    goal_cfg = sources_cfg.get("goal_engine", {})
    if goal_cfg.get("enabled", False):
        from adapters.goal_adapter import GoalAdapter
        goal_adapter = GoalAdapter(
            bus=bus,
            memory_system=memory_system,
            agent_name=agent_cfg.get("name"),
            user_name=agent_cfg.get("user_name"),
            cooldown_seconds=goal_cfg.get("cooldown_seconds", 30),
            max_consecutive_goals=goal_cfg.get("max_consecutive_goals", 10),
            rest_seconds=goal_cfg.get("rest_seconds", 300),
        )
        processor.set_goal_adapter(goal_adapter)
        # Connect goal adapter to StreamMonitor for workspace awareness
        sophia.stream_monitor._goal_adapter = goal_adapter
        adapters.append(goal_adapter)

    # Telegram adapter
    tg_cfg = sources_cfg.get("telegram", {})
    if tg_cfg.get("enabled", False):
        token = tg_cfg.get("token", "")
        if token and not token.startswith("${"):
            from adapters.telegram_adapter import TelegramAdapter
            tg_adapter = TelegramAdapter(
                bus=bus,
                token=token,
                allowed_chat_ids=tg_cfg.get("allowed_chat_ids", []),
            )
            processor.register_response_handler("telegram", tg_adapter.handle_response)
            adapters.append(tg_adapter)
        else:
            logger.warning("[main] Telegram enabled but token not set — skipping")

    # ------------------------------------------------------------------
    # 5. FastAPI app (import from agent_server so all existing endpoints work)
    # ------------------------------------------------------------------
    from agent_server import app, set_shared_objects

    # Inject shared objects into agent_server so its routes use the same
    # sophia instance and can submit through the webui adapter.
    set_shared_objects(
        sophia_agent=sophia,
        memory_system_ref=memory_system,
        episodic_memory_ref=episodic_memory,
        memory_explorer_ref=memory_explorer,
        kgraph_ref=kgraph,
        webui_adapter_ref=webui_adapter,
    )

    # ------------------------------------------------------------------
    # 6. Run everything
    # ------------------------------------------------------------------
    import uvicorn

    uvicorn_config = uvicorn.Config(
        app,
        host="0.0.0.0",
        port=port,
        log_level="info",
    )
    server = uvicorn.Server(uvicorn_config)

    # Start all adapters
    for adapter in adapters:
        await adapter.start()

    logger.info(f"SophiaAMS v2 starting on port {port}")
    logger.info(f"  LLM: {os.getenv('LLM_API_BASE', 'http://localhost:1234/v1')}")
    logger.info(f"  Model: {os.getenv('LLM_MODEL', 'default')}")
    logger.info(f"  Adapters: {[type(a).__name__ for a in adapters]}")

    try:
        # Run uvicorn and event processor concurrently
        await asyncio.gather(
            server.serve(),
            processor.run(),
        )
    finally:
        # Graceful shutdown
        for adapter in reversed(adapters):
            try:
                await adapter.stop()
            except Exception as e:
                logger.error(f"Error stopping {type(adapter).__name__}: {e}")

        processor.stop()
        logger.info("SophiaAMS shutdown complete")


# ---------------------------------------------------------------------------
# Frontend subprocess management
# ---------------------------------------------------------------------------

def _spawn_and_register(cmd, cwd, label):
    """Spawn a subprocess, register atexit cleanup, return Popen handle."""
    # On Windows, node/npx/npm are .cmd files — need shell=True to resolve them
    use_shell = sys.platform == "win32"
    proc = subprocess.Popen(
        cmd,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        shell=use_shell,
    )

    def _kill():
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()

    atexit.register(_kill)
    logger.info(f"{label} started (PID {proc.pid})")
    return proc


def start_frontend_subprocesses():
    """Start the Node.js API proxy server AND the Vite React dev server.

    Returns a list of Popen handles (may be empty if sophia-web isn't set up).
    """
    procs = []

    # --- Node.js API proxy server (port 3001) ---
    server_js = os.path.join(FRONTEND_DIR, "server", "server.js")
    server_modules = os.path.join(FRONTEND_DIR, "server", "node_modules")
    if os.path.isfile(server_js) and os.path.isdir(server_modules):
        procs.append(_spawn_and_register(
            ["node", server_js],
            cwd=os.path.join(FRONTEND_DIR, "server"),
            label="Node.js API server (port 3001)",
        ))
    else:
        logger.warning("sophia-web/server not ready — run 'npm install' in sophia-web/server")

    # --- Vite React dev server (port 3000) ---
    client_dir = os.path.join(FRONTEND_DIR, "client")
    client_modules = os.path.join(client_dir, "node_modules")
    if os.path.isdir(client_dir) and os.path.isdir(client_modules):
        # Use npx vite so it works cross-platform without a global install
        procs.append(_spawn_and_register(
            ["npx", "vite"],
            cwd=client_dir,
            label="Vite React dev server (port 3000)",
        ))
    else:
        logger.warning("sophia-web/client not ready — run 'npm install' in sophia-web/client")

    return procs


# ---------------------------------------------------------------------------
# Setup mode
# ---------------------------------------------------------------------------

def _stop_procs(procs):
    """Terminate a list of subprocesses."""
    for proc in procs:
        if proc and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()


def run_setup_mode():
    """Run the minimal setup wizard server (first-run experience)."""
    import uvicorn
    from setup_server import app as setup_app

    port = int(os.getenv("AGENT_PORT", "5001"))

    # Start both Node.js server + Vite dev server
    frontend_procs = start_frontend_subprocesses()

    logger.info("=" * 60)
    logger.info("  FIRST-RUN SETUP WIZARD")
    logger.info("  Open http://localhost:3000 in your browser")
    logger.info("=" * 60)

    # Try to open browser automatically
    try:
        webbrowser.open("http://localhost:3000")
    except Exception:
        pass

    try:
        uvicorn.run(setup_app, host="0.0.0.0", port=port, log_level="info")
    finally:
        _stop_procs(frontend_procs)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    if not os.path.exists(SETUP_SENTINEL):
        logger.info("No .setup_complete found — entering setup mode")
        run_setup_mode()
    else:
        # Start frontend alongside the main application
        frontend_procs = start_frontend_subprocesses()
        try:
            asyncio.run(build_and_run())
        finally:
            _stop_procs(frontend_procs)


if __name__ == "__main__":
    main()
