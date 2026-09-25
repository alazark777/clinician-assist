"""Unit tests for Stage C real-model configuration detection."""

from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from harness.model_config import (
    apply_agent_model_env,
    credential_presence,
    real_model_configured,
    real_model_skip_reason,
)


class RealModelConfiguredTests(unittest.TestCase):
    """``real_model_configured`` environment rules."""

    def setUp(self) -> None:
        self._env = os.environ.copy()

    def tearDown(self) -> None:
        os.environ.clear()
        os.environ.update(self._env)

    def test_requires_explicit_backend(self) -> None:
        with patch.dict(
            os.environ,
            {"OPENAI_API_KEY": "k", "MODEL_ID": "gpt-4o-mini"},
            clear=True,
        ):
            self.assertFalse(real_model_configured())
            self.assertIn("MODEL_BACKEND not set", real_model_skip_reason())

    def test_stub_backend_never_runs(self) -> None:
        with patch.dict(
            os.environ,
            {
                "MODEL_BACKEND": "stub",
                "OPENAI_API_KEY": "k",
                "MODEL_ID": "gpt-4o-mini",
            },
            clear=True,
        ):
            self.assertFalse(real_model_configured())

    def test_rejects_stub_model_id(self) -> None:
        with patch.dict(
            os.environ,
            {
                "MODEL_BACKEND": "openai",
                "OPENAI_API_KEY": "k",
                "MODEL_ID": "offline-stub",
            },
            clear=True,
        ):
            self.assertFalse(real_model_configured())
            self.assertIn("MODEL_ID", real_model_skip_reason())

    def test_openai_backend_requires_key(self) -> None:
        with patch.dict(
            os.environ,
            {"MODEL_BACKEND": "openai", "MODEL_ID": "gpt-4o-mini"},
            clear=True,
        ):
            self.assertFalse(real_model_configured())
            self.assertIn("OPENAI_API_KEY", real_model_skip_reason())

    def test_openai_backend_ok(self) -> None:
        with patch.dict(
            os.environ,
            {
                "MODEL_BACKEND": "openai",
                "OPENAI_API_KEY": "k",
                "MODEL_ID": "gpt-4o-mini",
            },
            clear=True,
        ):
            self.assertTrue(real_model_configured())

    def test_google_backend_requires_key(self) -> None:
        with patch.dict(
            os.environ,
            {"MODEL_BACKEND": "google", "MODEL_ID": "gemini-2.5-flash-lite"},
            clear=True,
        ):
            self.assertFalse(real_model_configured())
            self.assertIn("GOOGLE_API_KEY", real_model_skip_reason())

    def test_google_backend_ok(self) -> None:
        with patch.dict(
            os.environ,
            {
                "MODEL_BACKEND": "google",
                "GOOGLE_API_KEY": "k",
                "MODEL_ID": "gemini-2.5-flash-lite",
            },
            clear=True,
        ):
            self.assertTrue(real_model_configured())

    def test_openai_key_does_not_enable_google(self) -> None:
        with patch.dict(
            os.environ,
            {
                "MODEL_BACKEND": "google",
                "OPENAI_API_KEY": "k",
                "MODEL_ID": "gemini-2.5-flash-lite",
            },
            clear=True,
        ):
            self.assertFalse(real_model_configured())

    def test_custom_backend_requires_key_and_base_url(self) -> None:
        with patch.dict(
            os.environ,
            {"MODEL_BACKEND": "custom", "MODEL_ID": "m", "MODEL_API_KEY": "k"},
            clear=True,
        ):
            self.assertFalse(real_model_configured())
            self.assertIn("MODEL_BASE_URL", real_model_skip_reason())

        with patch.dict(
            os.environ,
            {"MODEL_BACKEND": "custom", "MODEL_ID": "m", "MODEL_BASE_URL": "https://x/v1"},
            clear=True,
        ):
            self.assertFalse(real_model_configured())
            self.assertIn("MODEL_API_KEY", real_model_skip_reason())

    def test_custom_backend_ok(self) -> None:
        with patch.dict(
            os.environ,
            {
                "MODEL_BACKEND": "custom",
                "MODEL_API_KEY": "k",
                "MODEL_BASE_URL": "https://provider.example/v1",
                "MODEL_ID": "my-model",
            },
            clear=True,
        ):
            self.assertTrue(real_model_configured())

    def test_apply_agent_env_forwards_by_backend(self) -> None:
        with patch.dict(
            os.environ,
            {
                "EVAL_MODEL_BACKEND": "google",
                "GOOGLE_API_KEY": "g-secret",
                "MODEL_ID": "gemini-2.5-flash-lite",
            },
            clear=True,
        ):
            agent_env: dict[str, str] = {}
            apply_agent_model_env(agent_env)
            self.assertEqual(agent_env["MODEL_BACKEND"], "google")
            self.assertEqual(agent_env["GOOGLE_API_KEY"], "g-secret")
            self.assertNotIn("OPENAI_API_KEY", agent_env)

        with patch.dict(
            os.environ,
            {
                "EVAL_MODEL_BACKEND": "openai",
                "OPENAI_API_KEY": "o-secret",
                "OPENAI_BASE_URL": "https://gateway.example/v1",
                "MODEL_ID": "gpt-4o-mini",
            },
            clear=True,
        ):
            agent_env = {}
            apply_agent_model_env(agent_env)
            self.assertEqual(agent_env["OPENAI_API_KEY"], "o-secret")
            self.assertEqual(agent_env["OPENAI_BASE_URL"], "https://gateway.example/v1")

        with patch.dict(
            os.environ,
            {
                "EVAL_MODEL_BACKEND": "custom",
                "MODEL_API_KEY": "c-secret",
                "MODEL_BASE_URL": "https://provider/v1",
                "MODEL_ID": "m",
            },
            clear=True,
        ):
            agent_env = {}
            apply_agent_model_env(agent_env)
            self.assertEqual(agent_env["MODEL_API_KEY"], "c-secret")
            self.assertEqual(agent_env["MODEL_BASE_URL"], "https://provider/v1")

        with patch.dict(os.environ, {"MODEL_BACKEND": "openai", "OPENAI_API_KEY": "k"}, clear=True):
            agent_env = {}
            apply_agent_model_env(agent_env)
            self.assertEqual(agent_env["MODEL_BACKEND"], "stub")
            self.assertNotIn("OPENAI_API_KEY", agent_env)

    def test_credential_presence_never_includes_values(self) -> None:
        with patch.dict(
            os.environ,
            {
                "GOOGLE_API_KEY": "secret-google",
                "OPENAI_API_KEY": "secret-openai",
            },
            clear=True,
        ):
            presence = credential_presence()
            self.assertTrue(presence["google_api_key"])
            self.assertTrue(presence["openai_api_key"])
            self.assertNotIn("secret", str(presence))


if __name__ == "__main__":
    unittest.main()
