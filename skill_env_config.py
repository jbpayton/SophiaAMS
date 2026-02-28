"""
Skill environment variable configuration manager.

Discovers env vars used by skills (via static regex + optional LLM analysis),
stores configured values in skill_env_config.json, and applies them at startup.
"""

import json
import logging
import os
import re
import time
from typing import Dict, List, Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

CONFIG_FILE = os.path.join(os.path.dirname(__file__), "skill_env_config.json")

# Patterns to detect env var usage in Python files
_ENV_PATTERNS = [
    re.compile(r'os\.environ\.get\(\s*["\'](\w+)["\']'),
    re.compile(r'os\.environ\[\s*["\'](\w+)["\']'),
    re.compile(r'os\.getenv\(\s*["\'](\w+)["\']'),
]

# Internal vars managed by the system, not user-configurable
_INTERNAL_ENV_VARS = {"SOPHIA_SERVER_URL", "AGENT_PORT", "WORKSPACE_PATH", "SKILLS_PATH"}


def _is_sensitive_var(var_name: str) -> bool:
    """Determine if a variable name likely holds a secret vs a service endpoint."""
    # Service endpoint URLs and paths are not secrets
    non_sensitive_suffixes = ("_URL", "_BASE", "_HOST", "_PORT", "_PATH", "_DIR")
    return not var_name.upper().endswith(non_sensitive_suffixes)


def _mask_value(value: str, var_name: str = "") -> str:
    """Mask a secret value for safe display in API responses.

    Non-sensitive vars (URLs, hosts, paths) are shown in full.
    """
    if not value:
        return ""

    # Don't mask non-sensitive vars (service endpoints, paths, etc.)
    if var_name and not _is_sensitive_var(var_name):
        return value

    # URLs: show scheme + masked host
    if value.startswith("http://") or value.startswith("https://"):
        parsed = urlparse(value)
        host = parsed.hostname or ""
        masked_host = host[:3] + "\u2022\u2022\u2022" if len(host) > 3 else "\u2022\u2022\u2022"
        return f"{parsed.scheme}://{masked_host}"

    # Short values: fully mask
    if len(value) <= 8:
        return "\u2022" * 6

    # Longer values: first 3 + ••• + last 2
    return value[:3] + "\u2022\u2022\u2022" + value[-2:]


class SkillEnvConfig:
    """Manages environment variable configuration for skills."""

    def __init__(self, skill_loader=None):
        self.skill_loader = skill_loader
        self._config = self._load_config()

    def _load_config(self) -> dict:
        """Load config from disk."""
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {"env_vars": {}, "skill_analysis": {}, "skill_status": {}}

    def _save_config(self) -> None:
        """Persist config to disk."""
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(self._config, f, indent=2)

    def scan_skill_static(self, skill_path: str) -> List[str]:
        """Scan .py files in a skill directory for os.environ references."""
        env_vars = set()
        for root, _, files in os.walk(skill_path):
            for fname in files:
                if not fname.endswith(".py"):
                    continue
                fpath = os.path.join(root, fname)
                try:
                    with open(fpath, "r", encoding="utf-8", errors="replace") as f:
                        content = f.read()
                    for pattern in _ENV_PATTERNS:
                        env_vars.update(pattern.findall(content))
                except OSError:
                    pass
        return sorted(env_vars - _INTERNAL_ENV_VARS)

    def analyze_skill_llm(self, skill_name: str, skill_content: str, llm) -> List[str]:
        """Use LLM to discover env vars a skill needs."""
        messages = [
            {"role": "system", "content": (
                "You are analyzing a software skill/plugin. "
                "List ALL environment variables this skill needs to function. "
                "Return ONLY a JSON array of env var names, e.g. [\"API_KEY\", \"BASE_URL\"]. "
                "If none are needed, return []."
            )},
            {"role": "user", "content": f"Skill: {skill_name}\n\nContent:\n{skill_content[:3000]}"}
        ]

        try:
            response = llm.chat(messages, max_tokens=200)
            # Parse JSON array from response
            match = re.search(r'\[.*?\]', response, re.DOTALL)
            if match:
                return json.loads(match.group())
        except Exception as e:
            logger.error(f"LLM analysis failed for {skill_name}: {e}")

        return []

    def scan_skill(self, skill_name: str, llm=None) -> List[str]:
        """Full scan of a skill (static + optional LLM)."""
        if not self.skill_loader:
            return []

        skill = self.skill_loader.get_skill(skill_name)
        if not skill:
            return []

        # Static scan
        env_vars = self.scan_skill_static(skill.path)

        # LLM analysis
        if llm:
            skill_md = os.path.join(skill.path, "SKILL.md")
            try:
                with open(skill_md, "r", encoding="utf-8") as f:
                    content = f.read()
                llm_vars = self.analyze_skill_llm(skill_name, content, llm)
                env_vars = sorted(set(env_vars) | set(llm_vars))
            except OSError:
                pass

        # Cache results
        self._config.setdefault("skill_analysis", {})[skill_name] = env_vars
        self._save_config()

        return env_vars

    def check_env_var_health(self, value: str) -> dict:
        """Check health of an env var value. URLs get HTTP GET; others just non-empty check."""
        if not value:
            return {"ok": False, "error": "Value is empty"}

        # Check if it looks like a URL
        if value.startswith("http://") or value.startswith("https://"):
            import urllib.request
            import urllib.error

            base = value.rstrip("/")
            # Try the URL as-is first, then common health endpoints
            urls_to_try = [base, f"{base}/health", f"{base}/api/health"]

            last_error = None
            for url in urls_to_try:
                try:
                    req = urllib.request.Request(url, method="GET")
                    with urllib.request.urlopen(req, timeout=5) as resp:
                        if 200 <= resp.status < 300:
                            return {"ok": True, "error": None}
                        last_error = f"HTTP {resp.status}"
                except urllib.error.HTTPError as e:
                    if e.code == 404 and url != urls_to_try[-1]:
                        continue  # Try next endpoint
                    last_error = f"HTTP {e.code}"
                except urllib.error.URLError as e:
                    # Connection refused / unreachable — no point trying more paths
                    return {"ok": False, "error": str(e.reason)}
                except Exception as e:
                    return {"ok": False, "error": str(e)}

            # If we got 404 on all paths but the server responded, it's reachable
            if last_error and last_error == "HTTP 404":
                return {"ok": True, "error": None}

            return {"ok": False, "error": last_error or "Unknown error"}

        # Non-URL: just check non-empty
        return {"ok": True, "error": None}

    def get_skill_status(self, skill_name: str) -> dict:
        """Derive status for a skill from env var presence + cached test results."""
        env_vars = self._config.get("skill_analysis", {}).get(skill_name, [])

        # No env vars needed
        if not env_vars:
            return {"status": "no_env", "message": None}

        configured = self._config.get("env_vars", {})
        # Check if all vars have values
        all_configured = all(configured.get(v, "").strip() for v in env_vars)

        if not all_configured:
            return {"status": "unconfigured", "message": "Missing configuration"}

        # Check cached test results
        cached = self._config.get("skill_status", {}).get(skill_name)
        if cached:
            return {"status": cached["status"], "message": cached.get("message")}

        return {"status": "configured", "message": "Not tested"}

    def test_skill(self, skill_name: str) -> dict:
        """Run health check on all env vars for a skill. Cache and return results."""
        env_vars = self._config.get("skill_analysis", {}).get(skill_name, [])
        if not env_vars:
            return {"status": "no_env", "results": {}}

        configured = self._config.get("env_vars", {})
        results = {}
        all_ok = True

        for var in env_vars:
            value = configured.get(var, "")
            result = self.check_env_var_health(value)
            results[var] = result
            if not result["ok"]:
                all_ok = False

        status = "verified" if all_ok else "error"
        message = None if all_ok else "Health check failed"

        # Cache results
        self._config.setdefault("skill_status", {})[skill_name] = {
            "status": status,
            "message": message,
            "timestamp": time.time(),
            "var_results": results,
        }
        self._save_config()

        return {"status": status, "results": results}

    def get_all_skills_info(self) -> List[dict]:
        """Get info about all skills including discovered env vars."""
        if not self.skill_loader:
            return []

        skills = []
        for skill in self.skill_loader.list_skills():
            # Get cached analysis or do a quick static scan
            cached = self._config.get("skill_analysis", {}).get(skill.name)
            if cached is None:
                cached = self.scan_skill_static(skill.path)
                self._config.setdefault("skill_analysis", {})[skill.name] = cached
                self._save_config()

            skill_status = self.get_skill_status(skill.name)

            raw_values = {
                var: self._config.get("env_vars", {}).get(var, "")
                for var in cached
            }
            skills.append({
                "name": skill.name,
                "description": skill.description,
                "path": skill.path,
                "env_vars": cached,
                "configured_values": {
                    var: _mask_value(val, var) for var, val in raw_values.items()
                },
                "has_value": {
                    var: bool(val.strip()) for var, val in raw_values.items()
                },
                "status": skill_status["status"],
                "status_message": skill_status["message"],
            })

        return skills

    def get_all_env_vars(self) -> dict:
        """Get all configured env var values (masked for safe display)."""
        return {
            var: _mask_value(val, var)
            for var, val in self._config.get("env_vars", {}).items()
        }

    def set_env_var(self, var_name: str, value: str) -> None:
        """Set an env var value (persisted + applied immediately)."""
        self._config.setdefault("env_vars", {})[var_name] = value

        # Clear cached status for any skill using this var
        skill_analysis = self._config.get("skill_analysis", {})
        skill_status = self._config.get("skill_status", {})
        for skill_name, vars_list in skill_analysis.items():
            if var_name in vars_list and skill_name in skill_status:
                del skill_status[skill_name]

        self._save_config()
        os.environ[var_name] = value

    def remove_env_var(self, var_name: str) -> None:
        """Remove an env var."""
        self._config.get("env_vars", {}).pop(var_name, None)
        self._save_config()
        os.environ.pop(var_name, None)

    def apply_env_vars(self) -> None:
        """Apply all configured env vars to os.environ."""
        env_vars = self._config.get("env_vars", {})
        for var, value in env_vars.items():
            if value:  # Don't set empty values
                os.environ[var] = value
        if env_vars:
            logger.info(f"Applied {len(env_vars)} skill env vars")

    def scrub_secrets(self, text: str) -> str:
        """Replace any env var secret values found in text with [REDACTED]."""
        if not text:
            return text
        result = text
        for value in self._config.get("env_vars", {}).values():
            if value and len(value) > 3:
                result = result.replace(value, "[REDACTED]")
        return result
