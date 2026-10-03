"""Startup refuses an insecure configuration (backend/config.py)."""
import os
import subprocess
import sys
from pathlib import Path

import pytest

from helpers import OWNER

ROOT = Path(__file__).resolve().parent.parent


def _import_config(**overrides):
    """Import backend.config in a fresh interpreter: it validates at import time."""
    env = {**os.environ, **overrides}
    return subprocess.run(
        [sys.executable, "-c", "import backend.config as c; print(c.settings.ALLOWED_EMAIL)"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
    )


def test_a_valid_configuration_loads():
    result = _import_config()

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == OWNER


def test_a_missing_owner_stops_startup():
    result = _import_config(ALLOWED_EMAIL="")

    assert result.returncode != 0
    assert "ALLOWED_EMAIL must be set" in result.stderr


@pytest.mark.parametrize("secret", ["", "change-me", "dev-insecure-change-me"])
def test_a_missing_or_placeholder_secret_key_stops_startup(secret):
    result = _import_config(SECRET_KEY=secret)

    assert result.returncode != 0
    assert "SECRET_KEY must be set to a random value" in result.stderr


def test_the_owner_address_is_trimmed_and_lower_cased():
    result = _import_config(ALLOWED_EMAIL="  Owner@Example.COM ")

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "owner@example.com"
