"""Tests for skill_loader.py — use tmp_path fixture for temp SKILL.md files."""

import os
import shutil
import tempfile
import unittest

from skill_loader import SkillLoader, Skill


class TestSkillLoader(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _create_skill(self, name, description="A test skill", extra_content=""):
        skill_dir = os.path.join(self.tmpdir, name)
        os.makedirs(skill_dir, exist_ok=True)
        content = f"""---
name: {name}
description: {description}
---

# {name}

{extra_content}
"""
        with open(os.path.join(skill_dir, "SKILL.md"), "w") as f:
            f.write(content)
        return skill_dir

    def test_discovery(self):
        self._create_skill("skill-a")
        self._create_skill("skill-b")
        loader = SkillLoader([self.tmpdir])
        self.assertEqual(len(loader.list_skills()), 2)

    def test_frontmatter_parsing(self):
        self._create_skill("my-skill", description="Does cool things")
        loader = SkillLoader([self.tmpdir])
        skill = loader.get_skill("my-skill")
        self.assertIsNotNone(skill)
        self.assertEqual(skill.name, "my-skill")
        self.assertEqual(skill.description, "Does cool things")

    def test_missing_name_skip(self):
        """SKILL.md without name: field should be skipped."""
        skill_dir = os.path.join(self.tmpdir, "bad-skill")
        os.makedirs(skill_dir)
        with open(os.path.join(skill_dir, "SKILL.md"), "w") as f:
            f.write("---\ndescription: no name here\n---\n# Bad\n")

        loader = SkillLoader([self.tmpdir])
        self.assertEqual(len(loader.list_skills()), 0)

    def test_descriptions_format(self):
        self._create_skill("alpha", description="First skill")
        self._create_skill("beta", description="Second skill")
        loader = SkillLoader([self.tmpdir])
        desc = loader.descriptions()
        self.assertIn("alpha", desc)
        self.assertIn("First skill", desc)
        self.assertIn("beta", desc)

    def test_refresh(self):
        self._create_skill("initial")
        loader = SkillLoader([self.tmpdir])
        self.assertEqual(len(loader.list_skills()), 1)

        self._create_skill("added")
        loader.refresh()
        self.assertEqual(len(loader.list_skills()), 2)

    def test_no_frontmatter(self):
        """SKILL.md without --- frontmatter should be skipped."""
        skill_dir = os.path.join(self.tmpdir, "no-fm")
        os.makedirs(skill_dir)
        with open(os.path.join(skill_dir, "SKILL.md"), "w") as f:
            f.write("# Just markdown\nNo frontmatter here.\n")

        loader = SkillLoader([self.tmpdir])
        self.assertEqual(len(loader.list_skills()), 0)

    def test_empty_skill_paths(self):
        loader = SkillLoader(["/nonexistent/path"])
        self.assertEqual(len(loader.list_skills()), 0)
        self.assertEqual(loader.descriptions(), "No skills available.")


if __name__ == "__main__":
    unittest.main()
