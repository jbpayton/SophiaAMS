---
name: skill-creator
description: Create new skills by writing SKILL.md files and optional scripts
---

# Skill Creator

Create new skills that you can use in future conversations.

## How Skills Work

A skill is a directory under `skills/` containing:
- `SKILL.md` — frontmatter with name/description + instructions + code examples
- `scripts/` (optional) — Python scripts the skill references

## Creating a New Skill

```run
import os

skill_name = "my-new-skill"
skill_dir = f"skills/learned/{skill_name}"
os.makedirs(skill_dir, exist_ok=True)

with open(f"{skill_dir}/SKILL.md", "w") as f:
    f.write("""---
name: my-new-skill
description: Description of what this skill does
---

# My New Skill

Instructions and code examples here.
""")

print(f"Created skill: {skill_dir}/SKILL.md")
```

## Guidelines
- Use `skills/learned/` for self-created skills (vs `skills/` for built-in)
- Keep SKILL.md focused and concise
- Include ```run code blocks with working examples
- Scripts should use only stdlib + packages already installed
