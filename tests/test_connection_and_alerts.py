"""Two deployment details that fail silently if they are wrong."""

from __future__ import annotations

import pytest

from gamesenze.alerts import Alerter
from gamesenze.db import uses_transaction_pooler


@pytest.mark.parametrize(
    ("dsn", "pooled"),
    [
        # Supabase transaction pooler — asyncpg needs its statement cache off.
        ("postgresql://postgres.ref:pw@aws-0-eu-west-2.pooler.supabase.com:6543/postgres", True),
        # Session pooler: still a pooler, and harmless to disable the cache.
        ("postgresql://postgres.ref:pw@aws-0-eu-west-2.pooler.supabase.com:5432/postgres", True),
        ("postgresql://user:pw@host:6543/db", True),
        ("postgresql://user:pw@pgbouncer.internal:5432/db", True),
        # Direct connections keep the cache.
        ("postgresql://postgres:pw@db.ref.supabase.co:5432/postgres", False),
        ("postgresql://postgres@127.0.0.1:5432/gamesenze", False),
        ("", False),
    ],
)
def test_pooled_connections_are_detected(dsn, pooled):
    assert uses_transaction_pooler(dsn) is pooled


def test_slack_webhooks_get_a_text_field():
    payload = Alerter("https://hooks.slack.com/services/T/B/x")._payload(
        "Unresolved QA flags", {"count": 3}
    )
    assert payload["text"] == "Unresolved QA flags"
    assert payload["count"] == 3


def test_discord_webhooks_get_a_content_field():
    # Posting `text` to Discord returns 400 and the alert vanishes. §8 says
    # failure must never be silent, so a lossy alert path is worse than none.
    payload = Alerter("https://discord.com/api/webhooks/1/tok")._payload(
        "Unresolved QA flags", {"count": 3}
    )
    assert payload == {"content": "Unresolved QA flags count=3"}
    assert "text" not in payload


def test_alerting_never_raises_even_with_an_unreachable_webhook():
    # An alert that fails to send must not turn a warning into an outage.
    alerter = Alerter("http://127.0.0.1:9/nope", timeout=0.05)
    alerter.alert("something broke")
    assert alerter.sent == [{"text": "something broke"}]


def test_the_two_sgo_callers_together_stay_under_the_rate_limit():
    """The Worker and the fallback share one 10 requests/minute allowance.

    Both can fire in the same minute — the fallback runs hourly whether or not
    the Worker is healthy. Exceeding the limit earns a 429, and since budget is
    reserved before the call, a 429 spends an object and returns no prices.
    """
    from gamesenze.config import (
        FALLBACK_MAX_CATCHUP,
        RATE_LIMITS_PER_MINUTE,
        WORKER_MAX_FIXTURES_PER_TICK,
    )

    combined = WORKER_MAX_FIXTURES_PER_TICK + FALLBACK_MAX_CATCHUP
    assert combined <= RATE_LIMITS_PER_MINUTE["sportsgameodds"]


def test_the_worker_constant_matches_config():
    """The Worker cannot import Python, so its cap is duplicated in TypeScript."""
    import re
    from pathlib import Path

    from gamesenze.config import WORKER_MAX_FIXTURES_PER_TICK

    source = Path("workers/snapshot/src/index.ts").read_text()
    match = re.search(r"const MAX_FIXTURES_PER_TICK = (\d+);", source)
    assert match, "the Worker's per-tick cap was renamed or removed"
    assert int(match.group(1)) == WORKER_MAX_FIXTURES_PER_TICK
