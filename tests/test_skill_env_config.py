"""Tests for skill_env_config.py — status tracking, health checks, and cache invalidation."""

import json
import os
import shutil
import tempfile
import unittest
from unittest.mock import patch, MagicMock
from urllib.error import HTTPError, URLError

from skill_env_config import SkillEnvConfig, CONFIG_FILE, _mask_value
from skill_loader import SkillLoader


class SkillEnvConfigTestBase(unittest.TestCase):
    """Base class that sets up a temp skills dir, a SkillLoader, and a temp config file."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.config_path = os.path.join(self.tmpdir, "skill_env_config.json")

        # Patch CONFIG_FILE to use our temp path
        self._config_patch = patch("skill_env_config.CONFIG_FILE", self.config_path)
        self._config_patch.start()

        # Create skill dirs with SKILL.md + .py files
        self.skills_dir = os.path.join(self.tmpdir, "skills")
        os.makedirs(self.skills_dir)

    def tearDown(self):
        self._config_patch.stop()
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _create_skill(self, name, description="A test skill", env_vars=None):
        """Create a skill dir with SKILL.md and optionally a .py that references env vars."""
        skill_dir = os.path.join(self.skills_dir, name)
        os.makedirs(skill_dir, exist_ok=True)

        with open(os.path.join(skill_dir, "SKILL.md"), "w") as f:
            f.write(f"---\nname: {name}\ndescription: {description}\n---\n# {name}\n")

        if env_vars:
            lines = [f'import os\n']
            for var in env_vars:
                lines.append(f'{var.lower()} = os.environ.get("{var}", "")\n')
            with open(os.path.join(skill_dir, "main.py"), "w") as f:
                f.writelines(lines)

        return skill_dir

    def _make_config(self, env_vars=None, skill_analysis=None, skill_status=None):
        """Write a pre-populated config file."""
        data = {
            "env_vars": env_vars or {},
            "skill_analysis": skill_analysis or {},
            "skill_status": skill_status or {},
        }
        with open(self.config_path, "w") as f:
            json.dump(data, f)

    def _read_config(self):
        with open(self.config_path, "r") as f:
            return json.load(f)

    def _make_loader_and_config(self):
        loader = SkillLoader([self.skills_dir])
        config = SkillEnvConfig(loader)
        return loader, config


# ============================================================================
# Status derivation (get_skill_status)
# ============================================================================

class TestGetSkillStatus(SkillEnvConfigTestBase):

    def test_no_env_vars_returns_no_env(self):
        self._create_skill("simple-skill")
        self._make_config(skill_analysis={"simple-skill": []})
        _, config = self._make_loader_and_config()

        status = config.get_skill_status("simple-skill")
        self.assertEqual(status["status"], "no_env")

    def test_missing_values_returns_unconfigured(self):
        self._create_skill("web-search", env_vars=["SEARXNG_URL"])
        self._make_config(
            skill_analysis={"web-search": ["SEARXNG_URL"]},
            env_vars={},  # nothing configured
        )
        _, config = self._make_loader_and_config()

        status = config.get_skill_status("web-search")
        self.assertEqual(status["status"], "unconfigured")

    def test_empty_string_value_counts_as_unconfigured(self):
        self._create_skill("web-search", env_vars=["SEARXNG_URL"])
        self._make_config(
            skill_analysis={"web-search": ["SEARXNG_URL"]},
            env_vars={"SEARXNG_URL": "   "},  # whitespace only
        )
        _, config = self._make_loader_and_config()

        status = config.get_skill_status("web-search")
        self.assertEqual(status["status"], "unconfigured")

    def test_all_values_set_no_cache_returns_configured(self):
        self._create_skill("web-search", env_vars=["SEARXNG_URL"])
        self._make_config(
            skill_analysis={"web-search": ["SEARXNG_URL"]},
            env_vars={"SEARXNG_URL": "http://localhost:8088"},
        )
        _, config = self._make_loader_and_config()

        status = config.get_skill_status("web-search")
        self.assertEqual(status["status"], "configured")

    def test_cached_verified_returned(self):
        self._create_skill("web-search", env_vars=["SEARXNG_URL"])
        self._make_config(
            skill_analysis={"web-search": ["SEARXNG_URL"]},
            env_vars={"SEARXNG_URL": "http://localhost:8088"},
            skill_status={"web-search": {"status": "verified", "message": None}},
        )
        _, config = self._make_loader_and_config()

        status = config.get_skill_status("web-search")
        self.assertEqual(status["status"], "verified")

    def test_cached_error_returned(self):
        self._create_skill("web-search", env_vars=["SEARXNG_URL"])
        self._make_config(
            skill_analysis={"web-search": ["SEARXNG_URL"]},
            env_vars={"SEARXNG_URL": "http://bad-host"},
            skill_status={"web-search": {"status": "error", "message": "Health check failed"}},
        )
        _, config = self._make_loader_and_config()

        status = config.get_skill_status("web-search")
        self.assertEqual(status["status"], "error")
        self.assertIn("failed", status["message"])

    def test_partially_configured_is_unconfigured(self):
        """If a skill needs 2 vars and only 1 is set, status is unconfigured."""
        self._create_skill("multi", env_vars=["VAR_A", "VAR_B"])
        self._make_config(
            skill_analysis={"multi": ["VAR_A", "VAR_B"]},
            env_vars={"VAR_A": "set", "VAR_B": ""},
        )
        _, config = self._make_loader_and_config()

        status = config.get_skill_status("multi")
        self.assertEqual(status["status"], "unconfigured")


# ============================================================================
# Health check (check_env_var_health)
# ============================================================================

class TestCheckEnvVarHealth(SkillEnvConfigTestBase):

    def test_empty_value_fails(self):
        _, config = self._make_loader_and_config()
        result = config.check_env_var_health("")
        self.assertFalse(result["ok"])
        self.assertIn("empty", result["error"])

    def test_non_url_nonempty_passes(self):
        _, config = self._make_loader_and_config()
        result = config.check_env_var_health("sk-abc123secretkey")
        self.assertTrue(result["ok"])
        self.assertIsNone(result["error"])

    @patch("urllib.request.urlopen")
    def test_url_200_passes(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        _, config = self._make_loader_and_config()
        result = config.check_env_var_health("http://localhost:8088/")
        self.assertTrue(result["ok"])

    @patch("urllib.request.urlopen")
    def test_url_404_on_all_paths_still_passes(self, mock_urlopen):
        """Server is reachable but no routes match — that's OK, server is up."""
        mock_urlopen.side_effect = HTTPError(
            url="http://localhost:8088/",
            code=404,
            msg="Not Found",
            hdrs=None,
            fp=None,
        )

        _, config = self._make_loader_and_config()
        result = config.check_env_var_health("http://localhost:8088/")
        self.assertTrue(result["ok"])

    @patch("urllib.request.urlopen")
    def test_url_500_fails(self, mock_urlopen):
        mock_urlopen.side_effect = HTTPError(
            url="http://localhost:8088/",
            code=500,
            msg="Internal Server Error",
            hdrs=None,
            fp=None,
        )

        _, config = self._make_loader_and_config()
        result = config.check_env_var_health("http://localhost:8088/")
        self.assertFalse(result["ok"])
        self.assertIn("500", result["error"])

    @patch("urllib.request.urlopen")
    def test_url_connection_refused(self, mock_urlopen):
        mock_urlopen.side_effect = URLError(reason="Connection refused")

        _, config = self._make_loader_and_config()
        result = config.check_env_var_health("http://localhost:9999/")
        self.assertFalse(result["ok"])
        self.assertIn("Connection refused", result["error"])

    @patch("urllib.request.urlopen")
    def test_url_timeout(self, mock_urlopen):
        mock_urlopen.side_effect = URLError(reason="timed out")

        _, config = self._make_loader_and_config()
        result = config.check_env_var_health("https://slow-server.example.com")
        self.assertFalse(result["ok"])
        self.assertIn("timed out", result["error"])

    def test_https_url_also_triggers_http_check(self):
        """Ensure https:// URLs go through the URL path, not the non-empty path."""
        _, config = self._make_loader_and_config()
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.side_effect = URLError(reason="test")
            result = config.check_env_var_health("https://example.com")
            self.assertFalse(result["ok"])
            mock_urlopen.assert_called_once()


# ============================================================================
# test_skill() — integration with check_env_var_health
# ============================================================================

class TestTestSkill(SkillEnvConfigTestBase):

    def test_no_env_vars_returns_no_env(self):
        self._create_skill("simple")
        self._make_config(skill_analysis={"simple": []})
        _, config = self._make_loader_and_config()

        result = config.test_skill("simple")
        self.assertEqual(result["status"], "no_env")
        self.assertEqual(result["results"], {})

    @patch("urllib.request.urlopen")
    def test_all_pass_returns_verified(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        self._create_skill("web-search", env_vars=["SEARXNG_URL"])
        self._make_config(
            skill_analysis={"web-search": ["SEARXNG_URL"]},
            env_vars={"SEARXNG_URL": "http://localhost:8088"},
        )
        _, config = self._make_loader_and_config()

        result = config.test_skill("web-search")
        self.assertEqual(result["status"], "verified")
        self.assertTrue(result["results"]["SEARXNG_URL"]["ok"])

        # Verify it was cached to disk
        disk = self._read_config()
        self.assertEqual(disk["skill_status"]["web-search"]["status"], "verified")
        self.assertIn("timestamp", disk["skill_status"]["web-search"])

    def test_empty_var_returns_error(self):
        self._create_skill("web-search", env_vars=["SEARXNG_URL"])
        self._make_config(
            skill_analysis={"web-search": ["SEARXNG_URL"]},
            env_vars={"SEARXNG_URL": ""},
        )
        _, config = self._make_loader_and_config()

        result = config.test_skill("web-search")
        self.assertEqual(result["status"], "error")
        self.assertFalse(result["results"]["SEARXNG_URL"]["ok"])

    @patch("urllib.request.urlopen")
    def test_mixed_results_returns_error(self, mock_urlopen):
        """One URL ok, one var empty → overall error."""
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        self._create_skill("multi", env_vars=["API_URL", "API_KEY"])
        self._make_config(
            skill_analysis={"multi": ["API_URL", "API_KEY"]},
            env_vars={"API_URL": "http://localhost:5000", "API_KEY": ""},
        )
        _, config = self._make_loader_and_config()

        result = config.test_skill("multi")
        self.assertEqual(result["status"], "error")
        self.assertTrue(result["results"]["API_URL"]["ok"])
        self.assertFalse(result["results"]["API_KEY"]["ok"])


# ============================================================================
# set_env_var() — cache invalidation
# ============================================================================

class TestSetEnvVarCacheInvalidation(SkillEnvConfigTestBase):

    def test_saving_var_clears_cached_status(self):
        self._create_skill("web-search", env_vars=["SEARXNG_URL"])
        self._make_config(
            skill_analysis={"web-search": ["SEARXNG_URL"]},
            env_vars={"SEARXNG_URL": "http://old-url"},
            skill_status={"web-search": {"status": "verified", "message": None}},
        )
        _, config = self._make_loader_and_config()

        # Precondition: status is cached as verified
        self.assertEqual(config.get_skill_status("web-search")["status"], "verified")

        # Save a new value
        config.set_env_var("SEARXNG_URL", "http://new-url")

        # Status should reset to configured (cache cleared)
        self.assertEqual(config.get_skill_status("web-search")["status"], "configured")

        # Verify on disk too
        disk = self._read_config()
        self.assertNotIn("web-search", disk.get("skill_status", {}))

    def test_saving_var_clears_status_for_all_affected_skills(self):
        """If two skills share an env var, both get their cache cleared."""
        self._create_skill("skill-a", env_vars=["SHARED_URL"])
        self._create_skill("skill-b", env_vars=["SHARED_URL"])
        self._make_config(
            skill_analysis={
                "skill-a": ["SHARED_URL"],
                "skill-b": ["SHARED_URL"],
            },
            env_vars={"SHARED_URL": "http://old"},
            skill_status={
                "skill-a": {"status": "verified", "message": None},
                "skill-b": {"status": "error", "message": "Health check failed"},
            },
        )
        _, config = self._make_loader_and_config()

        config.set_env_var("SHARED_URL", "http://new")

        self.assertEqual(config.get_skill_status("skill-a")["status"], "configured")
        self.assertEqual(config.get_skill_status("skill-b")["status"], "configured")

    def test_saving_unrelated_var_preserves_cache(self):
        self._create_skill("web-search", env_vars=["SEARXNG_URL"])
        self._make_config(
            skill_analysis={"web-search": ["SEARXNG_URL"]},
            env_vars={"SEARXNG_URL": "http://localhost:8088"},
            skill_status={"web-search": {"status": "verified", "message": None}},
        )
        _, config = self._make_loader_and_config()

        config.set_env_var("UNRELATED_VAR", "some-value")

        # web-search status should still be verified
        self.assertEqual(config.get_skill_status("web-search")["status"], "verified")

    def test_set_env_var_applies_to_os_environ(self):
        self._create_skill("s")
        self._make_config()
        _, config = self._make_loader_and_config()

        config.set_env_var("TEST_VAR_XYZ", "hello")
        self.assertEqual(os.environ.get("TEST_VAR_XYZ"), "hello")

        # Cleanup
        os.environ.pop("TEST_VAR_XYZ", None)


# ============================================================================
# get_all_skills_info() — includes status fields
# ============================================================================

class TestGetAllSkillsInfo(SkillEnvConfigTestBase):

    def test_includes_status_and_message(self):
        self._create_skill("web-search", env_vars=["SEARXNG_URL"])
        self._create_skill("simple")
        self._make_config(
            skill_analysis={"web-search": ["SEARXNG_URL"], "simple": []},
            env_vars={"SEARXNG_URL": "http://localhost:8088"},
        )
        loader, config = self._make_loader_and_config()

        skills = config.get_all_skills_info()
        by_name = {s["name"]: s for s in skills}

        self.assertIn("status", by_name["web-search"])
        self.assertIn("status_message", by_name["web-search"])
        self.assertEqual(by_name["web-search"]["status"], "configured")

        self.assertEqual(by_name["simple"]["status"], "no_env")

    def test_unconfigured_skill_shows_unconfigured(self):
        self._create_skill("web-search", env_vars=["SEARXNG_URL"])
        self._make_config(
            skill_analysis={"web-search": ["SEARXNG_URL"]},
            env_vars={},
        )
        _, config = self._make_loader_and_config()

        skills = config.get_all_skills_info()
        ws = next(s for s in skills if s["name"] == "web-search")
        self.assertEqual(ws["status"], "unconfigured")

    def test_auto_scans_unknown_skills(self):
        """Skills not in skill_analysis get auto-scanned and appear in results."""
        self._create_skill("new-skill", env_vars=["NEW_VAR"])
        self._make_config()  # empty skill_analysis
        _, config = self._make_loader_and_config()

        skills = config.get_all_skills_info()
        ns = next(s for s in skills if s["name"] == "new-skill")
        self.assertIn("NEW_VAR", ns["env_vars"])
        self.assertEqual(ns["status"], "unconfigured")


# ============================================================================
# _mask_value()
# ============================================================================

class TestMaskValue(unittest.TestCase):

    def test_empty_returns_empty(self):
        self.assertEqual(_mask_value(""), "")

    def test_http_url_masked(self):
        result = _mask_value("http://192.168.2.94:1234")
        self.assertTrue(result.startswith("http://"))
        self.assertIn("\u2022\u2022\u2022", result)
        self.assertNotIn("168", result)

    def test_https_url_masked(self):
        result = _mask_value("https://api.example.com/v1")
        self.assertTrue(result.startswith("https://"))
        self.assertIn("\u2022\u2022\u2022", result)
        self.assertNotIn("example", result)

    def test_short_value_fully_masked(self):
        result = _mask_value("abc123")
        self.assertEqual(result, "\u2022" * 6)

    def test_exactly_8_chars_fully_masked(self):
        result = _mask_value("12345678")
        self.assertEqual(result, "\u2022" * 6)

    def test_long_value_shows_prefix_suffix(self):
        result = _mask_value("sk-abc123secretkey")
        self.assertTrue(result.startswith("sk-"))
        self.assertTrue(result.endswith("ey"))
        self.assertIn("\u2022\u2022\u2022", result)
        self.assertNotIn("secret", result)

    def test_9_char_value_shows_prefix_suffix(self):
        result = _mask_value("123456789")
        self.assertEqual(result, "123\u2022\u2022\u202289")


# ============================================================================
# scrub_secrets()
# ============================================================================

class TestScrubSecrets(SkillEnvConfigTestBase):

    def test_scrubs_secret_from_text(self):
        self._create_skill("s")
        self._make_config(env_vars={"API_KEY": "my-super-secret-key-12345"})
        _, config = self._make_loader_and_config()

        text = "The response was from my-super-secret-key-12345 endpoint"
        result = config.scrub_secrets(text)
        self.assertIn("[REDACTED]", result)
        self.assertNotIn("my-super-secret-key-12345", result)

    def test_skips_short_values(self):
        self._create_skill("s")
        self._make_config(env_vars={"FLAG": "yes"})
        _, config = self._make_loader_and_config()

        text = "The answer is yes or no"
        result = config.scrub_secrets(text)
        self.assertNotIn("[REDACTED]", result)
        self.assertEqual(result, text)

    def test_skips_empty_values(self):
        self._create_skill("s")
        self._make_config(env_vars={"EMPTY": ""})
        _, config = self._make_loader_and_config()

        text = "Nothing to scrub here"
        result = config.scrub_secrets(text)
        self.assertEqual(result, text)

    def test_scrubs_multiple_secrets(self):
        self._create_skill("s")
        self._make_config(env_vars={
            "KEY1": "secret-alpha-123",
            "KEY2": "secret-beta-456",
        })
        _, config = self._make_loader_and_config()

        text = "Found secret-alpha-123 and secret-beta-456 in output"
        result = config.scrub_secrets(text)
        self.assertEqual(result.count("[REDACTED]"), 2)
        self.assertNotIn("secret-alpha", result)
        self.assertNotIn("secret-beta", result)

    def test_returns_none_text_unchanged(self):
        self._create_skill("s")
        self._make_config(env_vars={"KEY": "secret"})
        _, config = self._make_loader_and_config()

        self.assertEqual(config.scrub_secrets(""), "")

    def test_url_value_scrubbed(self):
        self._create_skill("s")
        self._make_config(env_vars={"SVC_URL": "http://192.168.2.94:1234"})
        _, config = self._make_loader_and_config()

        text = "Connecting to http://192.168.2.94:1234/api/chat"
        result = config.scrub_secrets(text)
        self.assertIn("[REDACTED]", result)
        self.assertNotIn("192.168.2.94", result)


# ============================================================================
# get_all_skills_info() — masked values and has_value
# ============================================================================

class TestGetAllSkillsInfoMasked(SkillEnvConfigTestBase):

    def test_url_vars_shown_in_full(self):
        """URL endpoint vars (like SEARXNG_URL) are not masked — they're not secrets."""
        self._create_skill("web-search", env_vars=["SEARXNG_URL"])
        self._make_config(
            skill_analysis={"web-search": ["SEARXNG_URL"]},
            env_vars={"SEARXNG_URL": "http://192.168.2.94:8088"},
        )
        _, config = self._make_loader_and_config()

        skills = config.get_all_skills_info()
        ws = next(s for s in skills if s["name"] == "web-search")
        self.assertEqual(ws["configured_values"]["SEARXNG_URL"], "http://192.168.2.94:8088")

    def test_secret_vars_are_masked(self):
        """Vars that look like secrets (API keys, tokens) are masked."""
        self._create_skill("web-search", env_vars=["API_KEY"])
        self._make_config(
            skill_analysis={"web-search": ["API_KEY"]},
            env_vars={"API_KEY": "sk-secret-key-12345"},
        )
        _, config = self._make_loader_and_config()

        skills = config.get_all_skills_info()
        ws = next(s for s in skills if s["name"] == "web-search")
        self.assertNotIn("secret", ws["configured_values"]["API_KEY"])
        self.assertIn("\u2022\u2022\u2022", ws["configured_values"]["API_KEY"])

    def test_has_value_true_when_set(self):
        self._create_skill("web-search", env_vars=["SEARXNG_URL"])
        self._make_config(
            skill_analysis={"web-search": ["SEARXNG_URL"]},
            env_vars={"SEARXNG_URL": "http://localhost:8088"},
        )
        _, config = self._make_loader_and_config()

        skills = config.get_all_skills_info()
        ws = next(s for s in skills if s["name"] == "web-search")
        self.assertTrue(ws["has_value"]["SEARXNG_URL"])

    def test_has_value_false_when_empty(self):
        self._create_skill("web-search", env_vars=["SEARXNG_URL"])
        self._make_config(
            skill_analysis={"web-search": ["SEARXNG_URL"]},
            env_vars={"SEARXNG_URL": ""},
        )
        _, config = self._make_loader_and_config()

        skills = config.get_all_skills_info()
        ws = next(s for s in skills if s["name"] == "web-search")
        self.assertFalse(ws["has_value"]["SEARXNG_URL"])


# ============================================================================
# get_all_env_vars() — returns masked
# ============================================================================

class TestGetAllEnvVarsMasked(SkillEnvConfigTestBase):

    def test_returns_masked_values(self):
        self._create_skill("s")
        self._make_config(env_vars={"MY_SECRET": "super-secret-api-key-xyz"})
        _, config = self._make_loader_and_config()

        result = config.get_all_env_vars()
        self.assertIn("MY_SECRET", result)
        self.assertNotEqual(result["MY_SECRET"], "super-secret-api-key-xyz")
        self.assertIn("\u2022\u2022\u2022", result["MY_SECRET"])


if __name__ == "__main__":
    unittest.main()
