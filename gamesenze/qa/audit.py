"""Layer 6 — post-hoc audit (§5.6).

Runs daily via GitHub Actions, reviewing yesterday. Timing does not matter for
this job, which is exactly why it belongs on Actions rather than a Worker.

The weekly deeper pass re-verifies a random 10% of settled picks against a
third source. Silent settlement errors are the most damaging failure mode we
have: they corrupt the track record invisibly, and we would never know to look.
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

from ..alerts import Alerter
from ..budget import BudgetMeter
from ..db import Db

MIN_ODDS_COVERAGE_PCT = 90.0


def _day_bounds(day: date) -> tuple[datetime, datetime]:
    start = datetime.combine(day, time.min, tzinfo=UTC)
    return start, start + timedelta(days=1)


@dataclass
class AuditReport:
    audit_date: date
    picks_published: int = 0
    picks_blocked: int = 0
    block_reasons: dict[str, int] = field(default_factory=dict)
    qa_flags_raised: int = 0
    qa_flags_unresolved: int = 0
    score_mismatches: int = 0
    settlement_pending: int = 0
    odds_coverage_pct: float = 0.0
    api_budget_pct: dict[str, float] = field(default_factory=dict)
    scrape_failures: int = 0
    alerts: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "audit_date": self.audit_date.isoformat(),
            "picks_published": self.picks_published,
            "picks_blocked": self.picks_blocked,
            "block_reasons": self.block_reasons,
            "qa_flags_raised": self.qa_flags_raised,
            "qa_flags_unresolved": self.qa_flags_unresolved,
            "score_mismatches": self.score_mismatches,
            "settlement_pending": self.settlement_pending,
            "odds_coverage_pct": round(self.odds_coverage_pct, 2),
            "api_budget_pct": {k: round(v, 1) for k, v in self.api_budget_pct.items()},
            "scrape_failures": self.scrape_failures,
            "alerts": self.alerts,
        }


async def daily_audit(
    db: Db,
    audit_date: date,
    *,
    alerter: Alerter | None = None,
    meter: BudgetMeter | None = None,
) -> AuditReport:
    start, end = _day_bounds(audit_date)
    report = AuditReport(audit_date)
    alerter = alerter or Alerter()

    report.picks_published = int(
        await db.fetchval(
            "select count(*) from picks where published_at >= $1 and published_at < $2",
            start,
            end,
        )
        or 0
    )

    blocked_rows = await db.fetch(
        "select failed_checks from publication_blocks "
        "where blocked_at >= $1 and blocked_at < $2",
        start,
        end,
    )
    report.picks_blocked = len(blocked_rows)
    for row in blocked_rows:
        for check in row.get("failed_checks") or []:
            report.block_reasons[check] = report.block_reasons.get(check, 0) + 1

    report.qa_flags_raised = int(
        await db.fetchval(
            "select count(*) from qa_flags where raised_at >= $1 and raised_at < $2",
            start,
            end,
        )
        or 0
    )
    report.qa_flags_unresolved = int(
        await db.fetchval(
            "select count(*) from qa_flags where resolved_at is null "
            "and severity in ('block', 'review')"
        )
        or 0
    )
    report.score_mismatches = int(
        await db.fetchval(
            "select count(*) from qa_flags where issue = 'final_score_mismatch' "
            "and raised_at >= $1 and raised_at < $2",
            start,
            end,
        )
        or 0
    )
    report.settlement_pending = int(
        await db.fetchval(
            """
            select count(*) from picks p
            join fixtures f on f.id = p.fixture_id
            where p.status = 'published' and f.status = 'finished'
              and f.kickoff_at >= $1 and f.kickoff_at < $2
              and p.result is null
            """,
            start,
            end,
        )
        or 0
    )
    report.scrape_failures = int(
        await db.fetchval(
            "select count(*) from scrape_runs where status = 'failed' "
            "and started_at >= $1 and started_at < $2",
            start,
            end,
        )
        or 0
    )

    # Odds coverage: of the fixtures we said we would cover, how many actually
    # got a capture yesterday. A covered fixture with no odds is a pick we
    # cannot price, and it is invisible unless counted.
    covered = int(
        await db.fetchval(
            "select count(*) from fixtures where covered "
            "and kickoff_at >= $1 and kickoff_at < $2 + interval '48 hours'",
            start,
            end,
        )
        or 0
    )
    with_odds = int(
        await db.fetchval(
            """
            select count(distinct f.id) from fixtures f
            join odds_snapshots o on o.fixture_id = f.id
            where f.covered
              and f.kickoff_at >= $1 and f.kickoff_at < $2 + interval '48 hours'
              and o.captured_at >= $1 and o.captured_at < $2
            """,
            start,
            end,
        )
        or 0
    )
    report.odds_coverage_pct = 100.0 if covered == 0 else 100.0 * with_odds / covered

    if meter is not None:
        for provider, status in (await meter.all_statuses()).items():
            report.api_budget_pct[provider] = status.pct

    # --- Alerts -------------------------------------------------------------
    if report.qa_flags_unresolved > 0:
        message = (
            f"Unresolved QA flags ({report.qa_flags_unresolved}) — review "
            "before next publication cycle"
        )
        report.alerts.append(message)
        alerter.alert(message, audit_date=audit_date.isoformat())

    if covered > 0 and report.odds_coverage_pct < MIN_ODDS_COVERAGE_PCT:
        message = (
            f"Odds coverage {report.odds_coverage_pct:.1f}% — investigate"
        )
        report.alerts.append(message)
        alerter.alert(message, audit_date=audit_date.isoformat())

    if report.score_mismatches > 0:
        message = (
            f"{report.score_mismatches} score mismatch(es) — settlement halted "
            "until resolved"
        )
        report.alerts.append(message)
        alerter.alert(message, audit_date=audit_date.isoformat())

    if report.scrape_failures > 0:
        message = f"{report.scrape_failures} scrape failure(s) yesterday"
        report.alerts.append(message)
        alerter.alert(message, audit_date=audit_date.isoformat())

    for provider, pct in report.api_budget_pct.items():
        if pct >= 85.0:
            message = f"{provider} at {pct:.0f}% of ceiling — above the 85% band"
            report.alerts.append(message)
            alerter.alert(message, provider=provider)

    await db.execute(
        """
        insert into daily_audit_reports (audit_date, report, alerted)
        values ($1, $2, $3)
        on conflict (audit_date) do update
            set report = excluded.report,
                alerted = excluded.alerted,
                generated_at = now()
        """,
        audit_date,
        json.dumps(report.to_dict()),
        bool(report.alerts),
    )
    return report


async def weekly_sample_audit(
    db: Db,
    *,
    since: datetime,
    fraction: float = 0.10,
    rng: random.Random | None = None,
) -> list[dict[str, Any]]:
    """Pick a random 10% of settled picks for third-source re-verification.

    Returns the sample; the actual third-source comparison is done by the
    caller, which owns the vendor budget. Sampling is separated from verifying
    so the selection is reproducible with a seeded rng in tests.
    """
    if not 0 < fraction <= 1:
        raise ValueError("fraction must be in (0, 1]")

    settled = await db.fetch(
        "select id, fixture_id, market, selection, result, settled_at "
        "from picks where status = 'settled' and settled_at >= $1",
        since,
    )
    if not settled:
        return []

    rng = rng or random.Random()
    # Round up: at low volume a 10% sample of 9 picks must not be zero.
    k = max(1, -(-len(settled) * int(fraction * 100) // 100))
    return rng.sample(settled, min(k, len(settled)))
