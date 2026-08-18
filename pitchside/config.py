"""Configuration and the numbers from the PRD that code needs to agree on.

Anything that appears as a table in the PRD lives here as data, not scattered
through the modules that use it. When a ceiling changes, it changes once.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

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
    "sportsgameodds": ProviderBudget("sportsgameodds", 2500, "month", 2000),
    # Open-Meteo is unlimited but still metered, so the audit can show what we
    # actually leaned on.
    "open_meteo": ProviderBudget("open_meteo", 0, "day", 0),
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


@dataclass(frozen=True)
class Settings:
    database_url: str = ""
    api_football_key: str = ""
    sportsgameodds_key: str = ""
    scraper_contact: str = ""
    alert_webhook_url: str = ""
    gh_dispatch_token: str = ""
    gh_repo: str = ""
    dry_run: bool = False
    excluded: tuple[str, ...] = field(default=())

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> Settings:
        e = os.environ if env is None else env
        return cls(
            database_url=e.get("DATABASE_URL", ""),
            api_football_key=e.get("API_FOOTBALL_KEY", ""),
            sportsgameodds_key=e.get("SPORTSGAMEODDS_KEY", ""),
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
    return f"PitchSide/{__import__('pitchside').__version__} (+{contact})"
