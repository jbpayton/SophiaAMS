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
            with open(script_path, "w", encoding="utf-8") as f:
                f.write(code)

            result = subprocess.run(
                [self.python_path, script_path],
                cwd=self.workspace,
                capture_output=True,
                text=True,
                timeout=self.timeout,
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
