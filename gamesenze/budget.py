"""Request budget metering — REQ-BUDGET-3.

Every vendor call increments `api_budget`. That is not bookkeeping for its own
sake: the degradation ladder in §8 reads these counters, so a call that skips
the meter is a call that can push us past a ceiling without anything noticing.

The increment happens *before* the request, not after. A call that is made and
then fails still consumed quota at the vendor, and counting it afterwards means
a crash between request and write leaves us believing we have room we do not.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .clock import Clock, SystemClock
from .config import PROVIDER_BUDGETS, ProviderBudget
from .db import Db


class BudgetExhausted(RuntimeError):
    """Raised instead of making a call that would breach a ceiling.

    Fail closed: at 100% we serve last-known data with a visible timestamp and
    publish no new picks (§8). We do not borrow against tomorrow.
    """

    def __init__(self, provider: str, used: int, limit: int) -> None:
        super().__init__(f"{provider} budget exhausted: {used}/{limit}")
        self.provider = provider
        self.used = used
        self.limit = limit


def period_key(budget: ProviderBudget, now: datetime) -> str:
    """'YYYY-MM-DD' for daily ceilings, 'YYYY-MM' for monthly ones."""
    if budget.period == "day":
        return now.strftime("%Y-%m-%d")
    if budget.period == "month":
        return now.strftime("%Y-%m")
    raise ValueError(f"unknown budget period {budget.period!r}")


@dataclass(frozen=True)
class BudgetStatus:
    provider: str
    period: str
    used: int
    limit: int

    @property
    def pct(self) -> float:
        if self.limit <= 0:
            return 0.0
        return 100.0 * self.used / self.limit

    @property
    def remaining(self) -> int:
        if self.limit <= 0:
            return 2**31
        return max(0, self.limit - self.used)

    @property
    def unlimited(self) -> bool:
        return self.limit <= 0


class BudgetMeter:
    """Reserve-then-call metering against `api_budget`."""

    def __init__(
        self,
        db: Db,
        clock: Clock | None = None,
        budgets: dict[str, ProviderBudget] | None = None,
    ) -> None:
        self._db = db
        self._clock = clock or SystemClock()
        self._budgets = budgets or PROVIDER_BUDGETS

    def budget_for(self, provider: str) -> ProviderBudget:
        try:
            return self._budgets[provider]
        except KeyError:
            raise ValueError(
                f"unknown provider {provider!r}: add it to PROVIDER_BUDGETS "
                "before metering against it"
            ) from None

    async def status(self, provider: str) -> BudgetStatus:
        budget = self.budget_for(provider)
        period = period_key(budget, self._clock.now())
        used = await self._db.fetchval(
            "select calls_used from api_budget where provider = $1 and period = $2",
            provider,
            period,
        )
        return BudgetStatus(provider, period, int(used or 0), budget.ceiling)

    async def reserve(
        self,
        provider: str,
        endpoint: str,
        *,
        cost: int = 1,
        job: str | None = None,
    ) -> BudgetStatus:
        """Claim `cost` units of quota, or raise `BudgetExhausted`.

        The claim is a single upsert with the ceiling check in the WHERE clause,
        so two jobs racing at the boundary cannot both win the last call.
        """
        budget = self.budget_for(provider)
        now = self._clock.now()
        period = period_key(budget, now)

        if budget.ceiling <= 0:  # unlimited provider: meter, never block
            await self._db.execute(
                """
                insert into api_budget (provider, period, calls_used, calls_limit,
                                        updated_at)
                values ($1, $2, $3, 0, $4)
                on conflict (provider, period) do update
                    set calls_used = api_budget.calls_used + $3,
                        updated_at = $4
                """,
                provider,
                period,
                cost,
                now,
            )
            await self._log_call(provider, endpoint, cost, job, now)
            return await self.status(provider)

        used = await self._db.fetchval(
            """
            insert into api_budget (provider, period, calls_used, calls_limit,
                                    updated_at)
            values ($1, $2, $3, $4, $5)
            on conflict (provider, period) do update
                set calls_used = api_budget.calls_used + $3,
                    calls_limit = excluded.calls_limit,
                    updated_at  = $5
                where api_budget.calls_used + $3 <= $4
            returning calls_used
            """,
            provider,
            period,
            cost,
            budget.ceiling,
            now,
        )

        if used is None:
            # The conditional update did not fire: we are at the ceiling.
            current = await self.status(provider)
            raise BudgetExhausted(provider, current.used, budget.ceiling)

        await self._log_call(provider, endpoint, cost, job, now)
        return BudgetStatus(provider, period, int(used), budget.ceiling)

    async def _log_call(
        self, provider: str, endpoint: str, cost: int, job: str | None, now: datetime
    ) -> None:
        await self._db.execute(
            """
            insert into api_calls (provider, endpoint, called_at, cost, job)
            values ($1, $2, $3, $4, $5)
            """,
            provider,
            endpoint,
            now,
            cost,
            job,
        )

    async def record_status_code(self, provider: str, code: int) -> None:
        """Attach the response code to the most recent call for this provider."""
        await self._db.execute(
            """
            update api_calls set status_code = $2
            where id = (select id from api_calls where provider = $1
                        order by called_at desc, id desc limit 1)
            """,
            provider,
            code,
        )

    async def all_statuses(self) -> dict[str, BudgetStatus]:
        return {p: await self.status(p) for p in self._budgets}
