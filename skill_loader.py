"""
File-based skill discovery using SKILL.md files with frontmatter.
Replaces LangChain tool registration.
"""

import os
from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class Skill:
    """A discovered skill from a SKILL.md file."""
    name: str
    description: str
    path: str  # Directory containing the SKILL.md


class SkillLoader:
    """
    Scans directories for SKILL.md files and parses their frontmatter
    to build a skill catalog. Skills are just files — the agent reads
    them and runs their scripts via normal code execution.
    """

    def __init__(self, skill_paths: List[str]):
        """
        Args:
            skill_paths: List of directories to scan for SKILL.md files.
        """
        self.skill_paths = [os.path.abspath(p) for p in skill_paths]
        self._skills: Dict[str, Skill] = {}
        self.refresh()

    def refresh(self) -> None:
        """Re-scan all skill paths and reload the catalog."""
        self._skills.clear()
        for base_path in self.skill_paths:
            if not os.path.isdir(base_path):
                continue
            for entry in os.listdir(base_path):
                skill_dir = os.path.join(base_path, entry)
                skill_file = os.path.join(skill_dir, "SKILL.md")
                if os.path.isdir(skill_dir) and os.path.isfile(skill_file):
                    skill = self._parse_skill(skill_file, skill_dir)
                    if skill:
                        self._skills[skill.name] = skill

    def _parse_skill(self, skill_file: str, skill_dir: str) -> Optional[Skill]:
        """Parse a SKILL.md file for frontmatter name and description."""
        try:
            with open(skill_file, "r", encoding="utf-8") as f:
                content = f.read()
        except OSError:
            return None

        # Parse --- delimited frontmatter
        if not content.startswith("---"):
            return None

        end = content.find("---", 3)
        if end == -1:
            return None

        frontmatter = content[3:end].strip()
        name = None
        description = None

        for line in frontmatter.split("\n"):
            line = line.strip()
            if line.lower().startswith("name:"):
                name = line[5:].strip().strip('"').strip("'")
            elif line.lower().startswith("description:"):
                description = line[12:].strip().strip('"').strip("'")

        if not name:
            return None

        return Skill(
            name=name,
            description=description or "",
            path=skill_dir,
        )

    def descriptions(self) -> str:
        """
        Format all skills as a string for inclusion in the system prompt.
        """
        if not self._skills:
            return "No skills available."

        lines = ["Available skills:"]
        for skill in sorted(self._skills.values(), key=lambda s: s.name):
            lines.append(f"  - {skill.name}: {skill.description}")
            skill_md = os.path.join(skill.path, "SKILL.md")
            lines.append(f"    Read: {skill_md}")
        return "\n".join(lines)

    def get_skill(self, name: str) -> Optional[Skill]:
        """Look up a skill by name."""
        return self._skills.get(name)

    def list_skills(self) -> List[Skill]:
        """Return all discovered skills."""
        return list(self._skills.values())
