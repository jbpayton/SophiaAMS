"""
Subprocess executor for running Python code in a workspace directory.
Replaces LangChain's PythonREPLTool / ShellTool.
"""

import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass


@dataclass
class RunResult:
    """Result of a code execution."""
    stdout: str
    stderr: str
    returncode: int

    @property
    def ok(self) -> bool:
        return self.returncode == 0

    def summary(self, max_chars: int = 5000) -> str:
        """Human-readable summary, truncated if needed."""
        parts = []
        if self.stdout:
            out = self.stdout if len(self.stdout) <= max_chars else self.stdout[:max_chars] + "\n[...truncated]"
            parts.append(out)
        if self.stderr:
            err = self.stderr if len(self.stderr) <= max_chars else self.stderr[:max_chars] + "\n[...truncated]"
            parts.append(f"STDERR:\n{err}")
        if not parts:
            return f"Process exited with code {self.returncode} (no output)"
        status = "OK" if self.ok else f"ERROR (code {self.returncode})"
        return f"[{status}]\n" + "\n".join(parts)


class CodeRunner:
    """
    Runs Python code strings in a sandboxed workspace directory.
    """

    MAX_OUTPUT = 50_000  # truncate stdout/stderr beyond this

    def __init__(
        self,
        workspace: str = "./workspace",
        timeout: int = 120,
        python_path: str = None,
    ):
        self.workspace = os.path.abspath(workspace)
        self.project_root = os.path.dirname(os.path.abspath(__file__))
        self.timeout = timeout
        self.python_path = python_path or sys.executable
        os.makedirs(self.workspace, exist_ok=True)

    def run(self, code: str) -> RunResult:
        """
        Execute a Python code string in the workspace directory.

        Args:
            code: Python source code to execute.

        Returns:
            RunResult with stdout, stderr, returncode.

        Raises:
            ValueError: If path traversal is detected in the code.
        """
        # Basic path traversal check
        if ".." in code and ("../" in code or "..\\" in code):
            return RunResult(
                stdout="",
                stderr="Security error: path traversal patterns (../ or ..\\..) are not allowed.",
                returncode=1,
            )

        # Write code to a temp file in the workspace
        script_path = os.path.join(self.workspace, "_run_tmp.py")
        try:
            # Prepend a preamble that makes skill paths resolve while
            # keeping file I/O sandboxed to the workspace directory.
            # - SOPHIA_ROOT env var points to the project root
            # - sys.path includes workspace (sophia_memory shim) and
            #   project root (for any project-level imports)
            # - The built-in open() is wrapped so that paths starting
            #   with "skills/" resolve against SOPHIA_ROOT, while all
            #   other relative paths resolve against workspace (cwd).
            preamble = (
                "import os as _os, sys as _sys, builtins as _builtins\n"
                f"_SOPHIA_ROOT = {self.project_root!r}\n"
                f"_os.environ['SOPHIA_ROOT'] = _SOPHIA_ROOT\n"
                f"_os.environ['WORKSPACE_PATH'] = {self.workspace!r}\n"
                f"_sys.path.insert(0, {self.workspace!r})\n"
                f"_sys.path.insert(0, _SOPHIA_ROOT)\n"
                "_original_open = _builtins.open\n"
                "def _patched_open(file, *a, **kw):\n"
                "    if isinstance(file, str) and file.startswith('skills/'):\n"
                "        file = _os.path.join(_SOPHIA_ROOT, file)\n"
                "    return _original_open(file, *a, **kw)\n"
                "_builtins.open = _patched_open\n"
            )

            with open(script_path, "w", encoding="utf-8") as f:
                f.write(preamble + code)

            env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
            result = subprocess.run(
                [self.python_path, script_path],
                cwd=self.workspace,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self.timeout,
                env=env,
            )

            stdout = result.stdout[:self.MAX_OUTPUT] if len(result.stdout) > self.MAX_OUTPUT else result.stdout
            stderr = result.stderr[:self.MAX_OUTPUT] if len(result.stderr) > self.MAX_OUTPUT else result.stderr

            return RunResult(
                stdout=stdout,
                stderr=stderr,
                returncode=result.returncode,
            )
        except subprocess.TimeoutExpired:
            return RunResult(
                stdout="",
                stderr=f"Execution timed out after {self.timeout} seconds.",
                returncode=1,
            )
        finally:
            # Clean up temp script
            if os.path.exists(script_path):
                try:
                    os.remove(script_path)
                except OSError:
                    pass
