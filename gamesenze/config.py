"""Configuration and the numbers from the PRD that code needs to agree on.

Anything that appears as a table in the PRD lives here as data, not scattered
through the modules that use it. When a ceiling changes, it changes once.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

# --- §1 operating principle -------------------------------------------------
# Run at 70-85% of every free-tier ceiling. The margin absorbs a re-run after a
# failed job, a longer-than-expected fixture list, or a source needing a second
# call. A pipeline tuned to 98% fails the first time anything goes wrong.
TARGET_UTILISATION = 0.80
UTILISATION_BAND = (0.70, 0.85)


@dataclass(frozen=True)
class ProviderBudget:
    """Ceiling and working target for one vendor (§3.1)."""

    name: str
    ceiling: int
    period: str  # 'day' | 'month'
    target: int  # what we plan to spend; the rest is reserve

    @property
    def reserve(self) -> int:
        return self.ceiling - self.target


PROVIDER_BUDGETS: dict[str, ProviderBudget] = {
    "api_football": ProviderBudget("api_football", 100, "day", 80),
    # Kept registered even though nothing calls it live any more (see
    # odds_api below): its free tier only covers MLS and the UEFA Champions
    # League for soccer, discovered live mid deployment, which does not
    # reach any of the leagues this product targets.
    "sportsgameodds": ProviderBudget("sportsgameodds", 2500, "month", 2000),
    # Open-Meteo is unlimited but still metered, so the audit can show what we
    # actually leaned on.
    "open_meteo": ProviderBudget("open_meteo", 0, "day", 0),
    # football-data.org's free tier: current-season fixtures for 9 of our 17
    # competitions (api-football's free tier only reaches 2022-2024, useless
    # for live picks). The real constraint is 10 req/min, not a daily count —
    # a daily ceiling still gives the existing degradation ladder something
    # to key off, set well above what 9 competitions synced once a day costs.
    "football_data": ProviderBudget("football_data", 500, "day", 100),
    # the-odds-api.com — replaces SportsGameOdds for live odds (§ see
    # providers/odds_api.py for why). One credit = one league's whole board,
    # so this is a monthly, not daily, ceiling. Reserve is generous because
    # odds_sync currently polls once/day (8 credits); the headroom is for
    # increasing that frequency later without a config change.
    "odds_api": ProviderBudget("odds_api", 500, "month", 400),
}


# --- §3.2 API-Football daily allocation (70 planned of 100, 30 reserve) -----
API_FOOTBALL_DAILY_ALLOCATION: dict[str, int] = {
    "fixture_sync": 8,
    "standings_refresh": 8,
    "injuries": 10,
    "confirmed_lineups": 12,
    "head_to_head": 5,
    "results_settlement": 12,
    "qa_cross_verification": 15,
}


# Per-minute rate limits, distinct from the monthly object ceilings above. The
# monthly budget says how much we may spend; these say how fast. Exceeding one
# earns a 429, and because we reserve budget *before* the call (REQ-BUDGET-3),
# a 429 costs us an object and returns nothing — the worst possible trade.
RATE_LIMITS_PER_MINUTE: dict[str, int] = {
    "sportsgameodds": 10,   # free "Amateur" plan
    "football_data": 10,    # free tier
}


def min_seconds_between_calls(provider: str) -> float:
    limit = RATE_LIMITS_PER_MINUTE.get(provider)
    return 0.0 if not limit else 60.0 / limit


# Two paths can call SportsGameOdds in the same minute: the Worker's per-minute
# tick, and the hourly fallback catching up on captures the Worker missed. They
# share one rate limit, so the caps are split rather than each assuming it has
# the whole allowance. Keep the sum at or below RATE_LIMITS_PER_MINUTE.
WORKER_MAX_FIXTURES_PER_TICK = 6
FALLBACK_MAX_CATCHUP = 3


# --- §3.3 SportsGameOdds monthly allocation --------------------------------
# One object = one full event across all books and markets.
SNAPSHOTS_PER_FIXTURE = 16
SNAPSHOTS_PER_NBA_GAME = 8

# Coverage cap is a product constraint as much as a technical one: roughly four
# football picks and two NBA picks a day, which is the curated volume the
# product calls for anyway.
MONTHLY_FOOTBALL_FIXTURE_CAP = 100
MONTHLY_NBA_GAME_CAP = 50


# --- §4.2 scraping discipline ----------------------------------------------
SCRAPE_MIN_INTERVAL_SECONDS = 6.0  # REQ-SCRAPE-1, per host
SCRAPE_WINDOW_UTC = (3, 6)  # REQ-SCRAPE-4, off-peak
PROVENANCE_RETENTION_DAYS = 60  # §7, raw_response pruning

# --- §9 storage -------------------------------------------------------------
SUPABASE_LIMIT_MB = 500
SUPABASE_ALERT_MB = 400


def _load_dotenv(path: Path | None = None) -> None:
    """Load KEY=VALUE lines from a .env file into the process environment.

    No dependency, no interpolation, no quoting rules beyond stripping simple
    wrapping quotes — this only needs to satisfy `.env.example`'s format.
    Real environment variables always win (`setdefault`, never overwrite), so
    a stray `.env` left in a checked-out repo can never shadow the values
    GitHub Actions injects via `env:` in a workflow.
    """
    path = path or Path.cwd() / ".env"
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


@dataclass(frozen=True)
class Settings:
    database_url: str = ""
    api_football_key: str = ""
    sportsgameodds_key: str = ""
    football_data_key: str = ""
    odds_api_key: str = ""
    scraper_contact: str = ""
    alert_webhook_url: str = ""
    gh_dispatch_token: str = ""
    gh_repo: str = ""
    dry_run: bool = False
    excluded: tuple[str, ...] = field(default=())

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> Settings:
        if env is None:
            _load_dotenv()
        e = os.environ if env is None else env
        return cls(
            database_url=e.get("DATABASE_URL", ""),
            api_football_key=e.get("API_FOOTBALL_KEY", ""),
            sportsgameodds_key=e.get("SPORTSGAMEODDS_KEY", ""),
            football_data_key=e.get("FOOTBALL_DATA_KEY", ""),
            odds_api_key=e.get("ODDS_API_KEY", ""),
            scraper_contact=e.get("SCRAPER_CONTACT", ""),
            alert_webhook_url=e.get("ALERT_WEBHOOK_URL", ""),
            gh_dispatch_token=e.get("GH_DISPATCH_TOKEN", ""),
            gh_repo=e.get("GH_REPO", ""),
            dry_run=e.get("DRY_RUN", "").lower() in ("1", "true", "yes"),
        )


def user_agent(contact: str) -> str:
    """REQ-SCRAPE-2: identify honestly, with a contact address.

    We do not disguise the scraper. A source that wants to block us should be
    able to, and should be able to reach us first.
    """
    if not contact:
        raise ValueError(
            "SCRAPER_CONTACT is required: REQ-SCRAPE-2 forbids an anonymous "
            "scraper"
        )
    return f"GameSenze/{__import__('gamesenze').__version__} (+{contact})"
