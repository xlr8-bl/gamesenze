/**
 * Time-critical scheduling — §2.2.
 *
 * GitHub Actions scheduled workflows do not run on time: 10-30 minute delays
 * are common under load, GitHub does not guarantee timing, and it does not
 * notify you when a scheduled run fails. That is fine for a nightly analysis
 * job and fatal for a T-1h lineup watch. So everything whose value decays in
 * minutes lives here instead.
 *
 * CPU discipline (§2.3, §9.6): the free tier allows 10ms CPU per invocation.
 * I/O wait does not count, so fetch-and-write passes — but only if it really
 * is fetch-and-write. This Worker never calls JSON.parse on a vendor payload:
 * it takes the response as text and splices it into a PostgREST insert as a
 * string. Flattening the object into odds rows happens in Postgres, in the
 * trigger in db/migrations/0005_ingest.sql, where CPU is free.
 *
 * Every failure path ends at a GitHub `workflow_dispatch`, which is the §8
 * fallback: "Cloudflare Worker fails -> GitHub Actions fallback catches it
 * within an hour."
 */

export interface Env {
  SUPABASE_URL: string;
  SUPABASE_SERVICE_ROLE_KEY: string;
  SPORTSGAMEODDS_KEY: string;
  API_FOOTBALL_KEY: string;
  GH_DISPATCH_TOKEN: string;
  GH_REPO: string;
}

interface DueSnapshot {
  fixture_id: string;
  vendor_event_id: string;
  window_label: string;
  kickoff_at: string;
}

interface DueLineup {
  fixture_id: string;
  vendor_fixture_id: string;
}

/** Cap per tick. The Worker request budget is vast (~200/day against 100k),
 *  but the vendor object budget is not, and a runaway tick would spend a
 *  month of SportsGameOdds objects in an afternoon. */
const MAX_FIXTURES_PER_TICK = 8;
const VENDOR_TIMEOUT_MS = 8000;

export default {
  async scheduled(event: ScheduledEvent, env: Env, ctx: ExecutionContext) {
    ctx.waitUntil(tick(env, event.cron));
  },

  /** Manual trigger, for the CPU verification in §10 and for debugging. */
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    if (url.pathname !== "/run") {
      return new Response("pitch-side snapshot worker", { status: 200 });
    }
    const started = Date.now();
    const result = await tick(env, "manual");
    return Response.json({ ...result, wall_ms: Date.now() - started });
  },
};

async function tick(env: Env, cron: string) {
  const summary = { odds: 0, lineups: 0, errors: [] as string[] };

  try {
    summary.odds = await captureOdds(env);
  } catch (err) {
    summary.errors.push(`odds: ${errorText(err)}`);
  }

  try {
    summary.lineups = await captureLineups(env);
  } catch (err) {
    summary.errors.push(`lineups: ${errorText(err)}`);
  }

  if (summary.errors.length > 0) {
    // Never swallow. §8: failure must never be silent.
    await dispatchFallback(env, "worker-fallback.yml", {
      cron,
      errors: summary.errors.join("; ").slice(0, 400),
    });
  }
  return summary;
}

// ---------------------------------------------------------------------------
// Odds capture
// ---------------------------------------------------------------------------

async function captureOdds(env: Env): Promise<number> {
  // All the §3.4 cadence arithmetic and the §8 ladder check happen in the
  // database function, so the Worker receives a short list and nothing else.
  const due = await rpc<DueSnapshot[]>(env, "due_odds_snapshots", {
    grace_minutes: 10,
    max_fixtures: MAX_FIXTURES_PER_TICK,
  });

  let written = 0;
  for (const item of due) {
    const raw = await fetchEventOdds(env, item.vendor_event_id);
    if (raw === null) continue;
    await enqueueOdds(env, item, raw);
    written += 1;
  }
  return written;
}

/** Returns the payload as *text*. Deliberately unparsed — see the CPU note. */
async function fetchEventOdds(
  env: Env,
  vendorEventId: string,
): Promise<string | null> {
  const response = await fetch(
    `https://api.sportsgameodds.com/v2/events/${vendorEventId}/odds`,
    {
      headers: { "X-Api-Key": env.SPORTSGAMEODDS_KEY },
      signal: AbortSignal.timeout(VENDOR_TIMEOUT_MS),
    },
  );
  if (!response.ok) return null;
  return await response.text();
}

async function enqueueOdds(env: Env, item: DueSnapshot, raw: string) {
  // String-built so the vendor body is never parsed in the Worker. JSON.stringify
  // is applied only to the short, known-safe fields around it.
  const body =
    `{"fixture_id":${JSON.stringify(item.fixture_id)},` +
    `"window_label":${JSON.stringify(item.window_label)},` +
    `"source":"sportsgameodds","payload":${raw}}`;

  const response = await fetch(`${env.SUPABASE_URL}/rest/v1/odds_ingest_queue`, {
    method: "POST",
    headers: { ...supabaseHeaders(env), Prefer: "return=minimal" },
    body,
  });
  if (!response.ok) {
    throw new Error(`enqueue ${response.status}: ${await response.text()}`);
  }
}

// ---------------------------------------------------------------------------
// Lineup watch — the reason this Worker exists.
// ---------------------------------------------------------------------------

async function captureLineups(env: Env): Promise<number> {
  const due = await rpc<DueLineup[]>(env, "due_lineup_checks", {
    max_fixtures: MAX_FIXTURES_PER_TICK,
  });

  let written = 0;
  for (const item of due) {
    const response = await fetch(
      `https://v3.football.api-sports.io/fixtures/lineups?fixture=${item.vendor_fixture_id}`,
      {
        headers: { "x-apisports-key": env.API_FOOTBALL_KEY },
        signal: AbortSignal.timeout(VENDOR_TIMEOUT_MS),
      },
    );
    if (!response.ok) continue;

    const raw = await response.text();
    const insert = await fetch(`${env.SUPABASE_URL}/rest/v1/lineup_ingest_queue`, {
      method: "POST",
      headers: { ...supabaseHeaders(env), Prefer: "return=minimal" },
      body:
        `{"fixture_id":${JSON.stringify(item.fixture_id)},` +
        `"source":"api_football","payload":${raw}}`,
    });
    if (insert.ok) written += 1;
  }
  return written;
}

// ---------------------------------------------------------------------------
// Plumbing
// ---------------------------------------------------------------------------

function supabaseHeaders(env: Env): Record<string, string> {
  return {
    apikey: env.SUPABASE_SERVICE_ROLE_KEY,
    Authorization: `Bearer ${env.SUPABASE_SERVICE_ROLE_KEY}`,
    "Content-Type": "application/json",
  };
}

async function rpc<T>(env: Env, name: string, args: unknown): Promise<T> {
  const response = await fetch(`${env.SUPABASE_URL}/rest/v1/rpc/${name}`, {
    method: "POST",
    headers: supabaseHeaders(env),
    body: JSON.stringify(args),
  });
  if (!response.ok) {
    throw new Error(`rpc ${name} ${response.status}: ${await response.text()}`);
  }
  return (await response.json()) as T;
}

/** §8: "Cloudflare Worker fails -> GitHub Actions fallback catches it." */
async function dispatchFallback(
  env: Env,
  workflow: string,
  inputs: Record<string, string>,
) {
  if (!env.GH_DISPATCH_TOKEN || !env.GH_REPO) return;
  await fetch(
    `https://api.github.com/repos/${env.GH_REPO}/actions/workflows/${workflow}/dispatches`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${env.GH_DISPATCH_TOKEN}`,
        Accept: "application/vnd.github+json",
        "Content-Type": "application/json",
        "User-Agent": "pitch-side-worker",
      },
      body: JSON.stringify({ ref: "main", inputs }),
    },
  );
}

function errorText(err: unknown): string {
  return err instanceof Error ? err.message : String(err);
}
