-- 0003_combo.sql — combo builder (§12).
-- Analytics and visualisation only: we store what the user assembled and,
-- optionally, what they report having placed elsewhere. We never hold funds,
-- forward a slip, or track an affiliate click.

create table if not exists combo_sessions (
    id                   uuid primary key default gen_random_uuid(),
    user_id              uuid not null,
    created_at           timestamptz not null default now(),
    pick_ids             jsonb not null,
    bookmaker_selections jsonb not null default '{}'::jsonb,
    total_odds           numeric(12, 4),
    expected_payout      numeric(12, 2),
    region               text,
    -- The snapshot the displayed prices came from, so the UI can render
    -- "as of 14:23 UTC" honestly rather than implying a live quote.
    odds_as_of           timestamptz
);

create index if not exists combo_sessions_user_idx
    on combo_sessions (user_id, created_at desc);

-- Optional self-reported log. Nothing here is executed by us.
create table if not exists combo_bets (
    id           uuid primary key default gen_random_uuid(),
    combo_id     uuid not null references combo_sessions (id) on delete cascade,
    user_id      uuid not null,
    bookmaker    text,
    odds_received numeric(12, 4) check (odds_received >= 1.01),
    stake_amount numeric(12, 2) check (stake_amount >= 0),
    placed_at    timestamptz,
    settled_at   timestamptz,
    result       text check (result in ('won', 'lost', 'void'))
);

create index if not exists combo_bets_user_idx on combo_bets (user_id, placed_at desc);
create index if not exists combo_bets_combo_idx on combo_bets (combo_id);

-- Legs are denormalised out of the jsonb for the analytics in §12 (win rate by
-- leg count, combo popularity, which picks get stacked together).
create table if not exists combo_legs (
    combo_id  uuid not null references combo_sessions (id) on delete cascade,
    pick_id   uuid not null references picks (id) on delete cascade,
    leg_index int not null,
    bookmaker text,
    odds      numeric(10, 3),
    primary key (combo_id, pick_id)
);

create index if not exists combo_legs_pick_idx on combo_legs (pick_id);

-- Row level security: a subscriber sees only their own combos.
alter table combo_sessions enable row level security;
alter table combo_bets enable row level security;

drop policy if exists combo_sessions_owner on combo_sessions;
create policy combo_sessions_owner on combo_sessions
    for all using (auth.uid() = user_id) with check (auth.uid() = user_id);

drop policy if exists combo_bets_owner on combo_bets;
create policy combo_bets_owner on combo_bets
    for all using (auth.uid() = user_id) with check (auth.uid() = user_id);
