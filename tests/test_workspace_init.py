"""Tests for workspace_init.py — use tmp_path (tempfile)."""

import os
import shutil
import tempfile
import unittest
import ast

from workspace_init import init_workspace


class TestWorkspaceInit(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_file_creation(self):
        path = init_workspace(self.tmpdir, "http://localhost:5001")
        self.assertTrue(os.path.exists(path))
        self.assertTrue(path.endswith("sophia_memory.py"))

    def test_base_url_embedding(self):
        path = init_workspace(self.tmpdir, "http://myhost:9999")
        with open(path) as f:
            content = f.read()
        self.assertIn("http://myhost:9999", content)

    def test_valid_python_syntax(self):
        path = init_workspace(self.tmpdir, "http://localhost:5001")
        with open(path) as f:
            content = f.read()
        # Should parse without syntax errors
        ast.parse(content)

    def test_directory_creation(self):
        new_dir = os.path.join(self.tmpdir, "subdir", "workspace")
        path = init_workspace(new_dir, "http://localhost:5001")
        self.assertTrue(os.path.exists(new_dir))
        self.assertTrue(os.path.exists(path))

    def test_overwrite(self):
        path1 = init_workspace(self.tmpdir, "http://first:5001")
        path2 = init_workspace(self.tmpdir, "http://second:5001")
        self.assertEqual(path1, path2)
        with open(path2) as f:
            content = f.read()
        self.assertIn("http://second:5001", content)
        self.assertNotIn("http://first:5001", content)

    def test_trailing_slash_stripped(self):
        path = init_workspace(self.tmpdir, "http://localhost:5001/")
        with open(path) as f:
            content = f.read()
        # Should not have double slashes in URLs
        self.assertNotIn("5001//", content)


if __name__ == "__main__":
    unittest.main()
