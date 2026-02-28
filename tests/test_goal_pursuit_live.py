#!/usr/bin/env python
"""
Live integration test: starts the server with a clean database,
creates a goal, and monitors the agent's pursuit in real-time.

Usage:
    python tests/test_goal_pursuit_live.py
    python tests/test_goal_pursuit_live.py --goal "Learn about black holes"
    python tests/test_goal_pursuit_live.py --timeout 120 --keep-data
"""

import argparse
import io
import json
import os
import shutil
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime

# Force UTF-8 stdout on Windows to avoid cp1252 encoding errors with box-drawing chars
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace", line_buffering=True)

# ── Config ──────────────────────────────────────────────────────────────────
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVER_PORT = int(os.environ.get("AGENT_PORT", "5001"))
BASE_URL = f"http://localhost:{SERVER_PORT}"
LOG_FILE = os.path.join(ROOT_DIR, "logs", "sophia.log")

WIPE_DIRS = [
    os.path.join(ROOT_DIR, "VectorKnowledgeGraphData"),
    os.path.join(ROOT_DIR, "data"),
    os.path.join(ROOT_DIR, "logs"),
]

# ANSI colors
C_RESET = "\033[0m"
C_DIM = "\033[2m"
C_BOLD = "\033[1m"
C_GREEN = "\033[32m"
C_YELLOW = "\033[33m"
C_RED = "\033[31m"
C_CYAN = "\033[36m"
C_MAGENTA = "\033[35m"


def ts():
    return datetime.now().strftime("%H:%M:%S")


def banner(msg):
    print(f"\n{C_BOLD}{C_CYAN}{'─' * 60}")
    print(f"  {msg}")
    print(f"{'─' * 60}{C_RESET}\n")


def info(msg):
    print(f"{C_DIM}[{ts()}]{C_RESET} {msg}")


def warn(msg):
    print(f"{C_DIM}[{ts()}]{C_RESET} {C_YELLOW}⚠ {msg}{C_RESET}")


def error(msg):
    print(f"{C_DIM}[{ts()}]{C_RESET} {C_RED}✗ {msg}{C_RESET}")


def success(msg):
    print(f"{C_DIM}[{ts()}]{C_RESET} {C_GREEN}✓ {msg}{C_RESET}")


# ── HTTP helpers ────────────────────────────────────────────────────────────

def api_get(path, timeout=5):
    url = f"{BASE_URL}{path}"
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def api_post(path, payload, timeout=30):
    url = f"{BASE_URL}{path}"
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def wait_for_server(max_wait=30):
    """Poll /health until the server responds."""
    info("Waiting for server to start...")
    start = time.time()
    while time.time() - start < max_wait:
        try:
            result = api_get("/health", timeout=2)
            if result.get("status") in ("ok", "healthy"):
                return True
        except Exception:
            pass
        time.sleep(1)
    return False


# ── Log monitor ─────────────────────────────────────────────────────────────

class LogMonitor:
    """Tail the log file and print interesting lines with color coding."""

    HIGHLIGHT_PATTERNS = {
        "Round ": C_BOLD + C_GREEN,
        "Token budget": C_DIM,
        "Clamping": C_YELLOW,
        "run blocks": C_GREEN,
        "empty after": C_RED,
        "retry succeeded": C_YELLOW,
        "searxng": C_CYAN,
        "web_search": C_CYAN,
        "web_read": C_CYAN,
        "web-search": C_CYAN,
        "web-read": C_CYAN,
        "goal_pursuit": C_MAGENTA,
        "GOAL_PURSUIT": C_MAGENTA,
        "mark_completed": C_BOLD + C_YELLOW,
        "mark_in_progress": C_GREEN,
        "set_goal": C_GREEN,
        "Error": C_RED,
        "ERROR": C_RED,
        "WARNING": C_YELLOW,
        "Journaled progress": C_BOLD + C_MAGENTA,
        "Processing chat": C_BOLD,
        "Processing goal": C_BOLD + C_MAGENTA,
        "finish_reason": C_DIM,
        "capping": C_YELLOW,
    }

    # Lines to suppress (too noisy)
    SUPPRESS = [
        "Suggesting next goal",
        "Querying goals",
        "Found 0 matching",
        "Found 0 goals",
        "No pending",
        "knowledge_graph' is empty",
        "Querying active goals",
        "Querying instrumental",
        "Querying high-priority",
        "No active goals found",
        "Getting active goals",
    ]

    def __init__(self, log_path):
        self.log_path = log_path
        self._pos = 0
        # Skip existing content
        if os.path.exists(log_path):
            self._pos = os.path.getsize(log_path)

    def poll(self):
        """Read new lines and print highlighted ones."""
        if not os.path.exists(self.log_path):
            return []

        interesting = []
        try:
            with open(self.log_path, "r", encoding="utf-8", errors="replace") as f:
                f.seek(self._pos)
                new_lines = f.readlines()
                self._pos = f.tell()
        except OSError:
            return []

        for line in new_lines:
            line = line.rstrip()
            if not line:
                continue

            # Suppress noisy lines
            if any(s in line for s in self.SUPPRESS):
                continue

            # Find the best highlight
            color = None
            for pattern, c in self.HIGHLIGHT_PATTERNS.items():
                if pattern.lower() in line.lower():
                    color = c
                    break

            if color:
                # Extract just the message part (after the logger name)
                parts = line.split(" - ", 3)
                if len(parts) >= 4:
                    msg = parts[3]
                else:
                    msg = line
                print(f"  {C_DIM}[{ts()}]{C_RESET} {color}{msg}{C_RESET}")
                interesting.append(line)

        return interesting


# ── Main flow ───────────────────────────────────────────────────────────────

def wipe_data():
    """Remove all persistent data for a clean start."""
    banner("WIPING DATA")
    for d in WIPE_DIRS:
        if os.path.exists(d):
            info(f"Removing {os.path.basename(d)}/")
            shutil.rmtree(d)
        else:
            info(f"{os.path.basename(d)}/ (already clean)")
    success("Data wiped")


def start_server():
    """Start main.py as a subprocess."""
    banner("STARTING SERVER")

    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"

    # Ensure logs dir exists
    os.makedirs(os.path.join(ROOT_DIR, "logs"), exist_ok=True)

    # Redirect stdout/stderr to a file instead of PIPE to avoid pipe buffer
    # deadlocks on Windows. The server (and its Node/Vite children) write a
    # lot of output — if nobody drains the pipe, the buffer fills and the
    # entire process tree blocks.
    server_log = os.path.join(ROOT_DIR, "logs", "server_stdout.log")
    stdout_file = open(server_log, "w", encoding="utf-8", errors="replace")

    proc = subprocess.Popen(
        [sys.executable, "main.py"],
        cwd=ROOT_DIR,
        env=env,
        stdout=stdout_file,
        stderr=subprocess.STDOUT,
    )

    # Stash the file handle so we can close it in cleanup
    proc._stdout_file = stdout_file

    info(f"Server PID: {proc.pid}")
    info(f"Server stdout → {server_log}")
    return proc


def create_goal(description, priority=4, retries=3):
    """Create a goal via the API."""
    banner(f"CREATING GOAL: {description}")
    for attempt in range(retries):
        try:
            result = api_post("/api/goals/create", {
                "description": description,
                "priority": priority,
                "owner": "Sophia",
            }, timeout=60)
            if result.get("success"):
                success(f"Goal created: {description} (priority={priority})")
            else:
                error(f"Failed to create goal: {result}")
            return result
        except Exception as e:
            if attempt < retries - 1:
                warn(f"Goal creation attempt {attempt+1} failed: {e} — retrying in 5s...")
                time.sleep(5)
            else:
                error(f"Goal creation failed after {retries} attempts: {e}")
                raise


def check_goal_status(description):
    """Check the current status of a goal."""
    goals = api_get("/api/goals")
    for g in goals.get("goals", []):
        if description.lower() in g["description"].lower():
            return g
    return None


def monitor_goal_pursuit(goal_desc, timeout_seconds, log_monitor):
    """Monitor the agent pursuing a goal until completion or timeout."""
    banner(f"MONITORING GOAL PURSUIT (timeout={timeout_seconds}s)")

    start = time.time()
    last_status_check = 0
    rounds_seen = 0
    searches_seen = 0
    completions_seen = 0

    while time.time() - start < timeout_seconds:
        # Poll logs
        interesting = log_monitor.poll()

        for line in interesting:
            line_lower = line.lower()
            if "round " in line_lower and "run blocks" in line_lower:
                rounds_seen += 1
            if "searxng" in line_lower or "web_search" in line_lower or "web-search" in line_lower:
                searches_seen += 1
            if "mark_completed" in line_lower or "journaled progress" in line_lower:
                completions_seen += 1

        # Check goal status periodically
        if time.time() - last_status_check > 10:
            last_status_check = time.time()
            try:
                goal = check_goal_status(goal_desc)
                if goal:
                    status = goal["status"]
                    if status == "completed":
                        print()
                        success(f"Goal completed!")
                        if goal.get("completion_notes"):
                            info(f"Notes: {goal['completion_notes'][:200]}")
                        break
                    elif status != "pending":
                        info(f"Goal status: {status}")
            except Exception as e:
                pass  # Server might be busy

        time.sleep(0.5)
    else:
        warn(f"Timeout after {timeout_seconds}s")

    # Print summary
    elapsed = time.time() - start
    print()
    banner("RESULTS")
    info(f"Time elapsed: {elapsed:.1f}s")
    info(f"Agent rounds seen: {rounds_seen}")
    info(f"Web searches seen: {searches_seen}")
    info(f"Goal completions seen: {completions_seen}")

    goal = None
    try:
        goal = check_goal_status(goal_desc)
    except Exception as e:
        warn(f"Could not check final goal status: {e}")
    if goal:
        info(f"Final goal status: {goal['status']}")
        if goal.get("completion_notes"):
            info(f"Completion notes: {goal['completion_notes'][:300]}")

    # Verdict
    print()
    if searches_seen > 0 and goal and goal["status"] == "completed":
        success("PASS - Goal completed with real web searches")
        return True
    elif searches_seen > 0:
        warn("PARTIAL - Web searches happened but goal not completed in time")
        return False
    elif goal and goal["status"] == "completed":
        error("FAIL - Goal marked complete WITHOUT any web searches (hallucinated)")
        return False
    else:
        warn("INCOMPLETE - Neither searches nor completion observed")
        return False


def main():
    parser = argparse.ArgumentParser(description="Live goal pursuit integration test")
    parser.add_argument("--goal", default="Learn about the Roman Empire",
                        help="Goal description to test")
    parser.add_argument("--priority", type=int, default=4,
                        help="Goal priority (1-5)")
    parser.add_argument("--timeout", type=int, default=180,
                        help="Max seconds to wait for goal completion")
    parser.add_argument("--keep-data", action="store_true",
                        help="Don't wipe data before starting")
    parser.add_argument("--no-server", action="store_true",
                        help="Don't start server (assume it's already running)")
    args = parser.parse_args()

    server_proc = None

    try:
        # Step 1: Wipe data
        if not args.keep_data and not args.no_server:
            wipe_data()

        # Step 2: Start server
        if not args.no_server:
            server_proc = start_server()

        # Step 3: Wait for server
        if not wait_for_server(max_wait=45):
            error("Server failed to start within 45s")
            # Dump server log
            server_log = os.path.join(ROOT_DIR, "logs", "server_stdout.log")
            if os.path.isfile(server_log):
                with open(server_log, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
                    if content:
                        print(content[-2000:])
            return 1

        success(f"Server is up at {BASE_URL}")

        # Step 4: Create the goal
        # Small delay to let adapters initialize
        time.sleep(3)
        create_goal(args.goal, args.priority)

        # Step 5: Monitor
        log_monitor = LogMonitor(LOG_FILE)
        passed = monitor_goal_pursuit(args.goal, args.timeout, log_monitor)

        return 0 if passed else 1

    except KeyboardInterrupt:
        warn("Interrupted by user")
        return 130

    finally:
        # Cleanup
        if server_proc:
            banner("STOPPING SERVER")
            server_proc.terminate()
            try:
                server_proc.wait(timeout=10)
                success("Server stopped")
            except subprocess.TimeoutExpired:
                server_proc.kill()
                warn("Server force-killed")
            # Close the stdout file handle
            if hasattr(server_proc, '_stdout_file'):
                try:
                    server_proc._stdout_file.close()
                except Exception:
                    pass


if __name__ == "__main__":
    sys.exit(main())
