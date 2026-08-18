-- 0008_dispatch_throttle.sql — stop the Worker stampeding GitHub Actions.
--
-- The Worker's cron fires every minute. `worker-fallback.yml` is dispatched
-- when a tick errors, and a persistent error — a missing vendor key, an expired
-- token, a vendor outage — is not one failure, it is one failure per minute.
-- At ~1 minute per run that is 1,440 minutes a day against a 2,000 minute
-- MONTHLY ceiling: the entire budget gone inside two days, and the §8 fallback
-- turned into the outage.
--
-- So a dispatch is a claim, not a notification. The Worker asks for a slot and
-- only calls GitHub if it wins one. `worker-fallback.yml` also runs hourly on
-- its own schedule, so a throttled dispatch delays recovery rather than
-- preventing it.

create table if not exists worker_dispatch_log (
    workflow        text primary key,
    last_dispatched timestamptz not null,
    dispatch_count  int not null default 1,
    last_reason     text
);

-- Atomically claim the right to dispatch, or return false.
--
-- The whole decision is one statement so two Workers racing at the boundary
-- cannot both win — which matters because "at most once an hour" enforced by a
-- read-then-write would be "twice an hour" under concurrency.
create or replace function claim_fallback_dispatch(
    p_workflow text,
    p_reason text default null,
    p_min_interval interval default interval '1 hour'
)
returns boolean
language plpgsql
as $$
declare
    claimed boolean;
begin
    insert into worker_dispatch_log (workflow, last_dispatched, last_reason)
    values (p_workflow, now(), p_reason)
    on conflict (workflow) do update
        set last_dispatched = now(),
            dispatch_count  = worker_dispatch_log.dispatch_count + 1,
            last_reason     = p_reason
        where worker_dispatch_log.last_dispatched < now() - p_min_interval
    returning true into claimed;

    return coalesce(claimed, false);
end;
$$;

-- Suppressed dispatches are still failures. Without this the throttle would
-- turn a loud problem into a quiet one, which is the opposite of §8.
create or replace view v_worker_dispatch_health as
select workflow,
       last_dispatched,
       dispatch_count,
       last_reason,
       now() - last_dispatched as since_last
  from worker_dispatch_log;
