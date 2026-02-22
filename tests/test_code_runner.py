"""Tests for code_runner.py — mock subprocess.run."""

import os
import subprocess
import unittest
from unittest.mock import patch, MagicMock

from code_runner import CodeRunner, RunResult


class TestRunResult(unittest.TestCase):
    def test_ok_property(self):
        r = RunResult(stdout="hello", stderr="", returncode=0)
        self.assertTrue(r.ok)

        r2 = RunResult(stdout="", stderr="err", returncode=1)
        self.assertFalse(r2.ok)

    def test_summary_ok(self):
        r = RunResult(stdout="output here", stderr="", returncode=0)
        s = r.summary()
        self.assertIn("[OK]", s)
        self.assertIn("output here", s)

    def test_summary_error(self):
        r = RunResult(stdout="", stderr="bad thing", returncode=1)
        s = r.summary()
        self.assertIn("ERROR", s)
        self.assertIn("bad thing", s)

    def test_summary_truncation(self):
        r = RunResult(stdout="x" * 100, stderr="", returncode=0)
        s = r.summary(max_chars=50)
        self.assertIn("[...truncated]", s)

    def test_summary_no_output(self):
        r = RunResult(stdout="", stderr="", returncode=0)
        s = r.summary()
        self.assertIn("no output", s)


class TestCodeRunner(unittest.TestCase):
    def test_success(self):
        runner = CodeRunner(workspace="/tmp/test_ws", timeout=10)
        mock_result = MagicMock()
        mock_result.stdout = "Hello World"
        mock_result.stderr = ""
        mock_result.returncode = 0

        with patch("subprocess.run", return_value=mock_result):
            with patch("builtins.open", MagicMock()):
                with patch("os.path.exists", return_value=True):
                    with patch("os.remove"):
                        result = runner.run("print('Hello World')")

        self.assertTrue(result.ok)
        self.assertEqual(result.stdout, "Hello World")

    def test_error(self):
        runner = CodeRunner(workspace="/tmp/test_ws", timeout=10)
        mock_result = MagicMock()
        mock_result.stdout = ""
        mock_result.stderr = "NameError: x"
        mock_result.returncode = 1

        with patch("subprocess.run", return_value=mock_result):
            with patch("builtins.open", MagicMock()):
                with patch("os.path.exists", return_value=True):
                    with patch("os.remove"):
                        result = runner.run("print(x)")

        self.assertFalse(result.ok)
        self.assertIn("NameError", result.stderr)

    def test_timeout(self):
        runner = CodeRunner(workspace="/tmp/test_ws", timeout=1)

        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="python", timeout=1)):
            with patch("builtins.open", MagicMock()):
                with patch("os.path.exists", return_value=True):
                    with patch("os.remove"):
                        result = runner.run("import time; time.sleep(100)")

        self.assertFalse(result.ok)
        self.assertIn("timed out", result.stderr)

    def test_workspace_creation(self):
        with patch("os.makedirs") as mock_makedirs:
            CodeRunner(workspace="/tmp/new_ws")
            mock_makedirs.assert_called_once_with(os.path.abspath("/tmp/new_ws"), exist_ok=True)

    def test_output_truncation(self):
        runner = CodeRunner(workspace="/tmp/test_ws", timeout=10)
        runner.MAX_OUTPUT = 100

        mock_result = MagicMock()
        mock_result.stdout = "x" * 200
        mock_result.stderr = ""
        mock_result.returncode = 0

        with patch("subprocess.run", return_value=mock_result):
            with patch("builtins.open", MagicMock()):
                with patch("os.path.exists", return_value=True):
                    with patch("os.remove"):
                        result = runner.run("print('x' * 200)")

        self.assertEqual(len(result.stdout), 100)

    def test_path_traversal_rejection(self):
        runner = CodeRunner(workspace="/tmp/test_ws", timeout=10)
        result = runner.run("open('../../../etc/passwd')")
        self.assertFalse(result.ok)
        self.assertIn("Security error", result.stderr)


if __name__ == "__main__":
    unittest.main()
