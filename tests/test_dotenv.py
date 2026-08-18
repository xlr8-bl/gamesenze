"""The README says "fill in .env" and expects that to be enough.

Nothing read .env until this fix — Settings.from_env() only checked real
environment variables, so a user following the README would hit a confusing
"DATABASE_URL is not set" with no clue why, having just set it.
"""

from __future__ import annotations

import pytest

from gamesenze.config import Settings


@pytest.fixture
def isolated_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    return tmp_path

def test_env_file_values_are_picked_up(isolated_cwd, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    (isolated_cwd / ".env").write_text("DATABASE_URL=postgresql://from-dotenv\n")

    assert Settings.from_env().database_url == "postgresql://from-dotenv"

def test_quoted_values_are_unwrapped(isolated_cwd, monkeypatch):
    monkeypatch.delenv("API_FOOTBALL_KEY", raising=False)
    (isolated_cwd / ".env").write_text(
        'API_FOOTBALL_KEY="double"\nSCRAPER_CONTACT=\'single@x.com\'\n'
    )

    settings = Settings.from_env()
    assert settings.api_football_key == "double"
    assert settings.scraper_contact == "single@x.com"

def test_comments_and_blank_lines_are_skipped(isolated_cwd, monkeypatch):
    monkeypatch.delenv("SCRAPER_CONTACT", raising=False)
    (isolated_cwd / ".env").write_text(
        "# a comment\n\nSCRAPER_CONTACT=ops@example.com\n"
    )

    assert Settings.from_env().scraper_contact == "ops@example.com"

def test_a_real_environment_variable_always_wins(isolated_cwd, monkeypatch):
    # CI injects secrets as real env vars via `env:` in the workflow. A stray
    # .env file left in the checked-out repo must never shadow that.
    (isolated_cwd / ".env").write_text("DATABASE_URL=postgresql://from-dotenv\n")
    monkeypatch.setenv("DATABASE_URL", "postgresql://from-ci")

    assert Settings.from_env().database_url == "postgresql://from-ci"

def test_missing_env_file_does_not_raise(isolated_cwd, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert not (isolated_cwd / ".env").exists()

    assert Settings.from_env().database_url == ""

def test_an_explicit_env_dict_bypasses_dotenv_entirely(isolated_cwd):
    # Passing `env=` explicitly (as the test suite does elsewhere) must not
    # trigger a filesystem read at all.
    (isolated_cwd / ".env").write_text("DATABASE_URL=postgresql://from-dotenv\n")

    settings = Settings.from_env({"DATABASE_URL": "postgresql://explicit"})
    assert settings.database_url == "postgresql://explicit"
