# Setup — getting every secret and variable

Work top to bottom; later steps need values from earlier ones. Budget about an
hour, most of it waiting for email confirmations.

Nothing here costs money. Every service is on a free tier and none of them
requires a card, with one exception noted under Netlify.

---

## 1. Supabase — 4 values

`SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, `DATABASE_URL`

1. Sign up at **supabase.com** → **New project**.
2. Pick the region closest to your readers. This is not easily changed later.
3. Set a **database password** and save it somewhere now — it is shown once and
   it goes inside `DATABASE_URL`. If you lose it, you can reset it under
   Settings → Database, but any stored connection string stops working.
4. Wait ~2 minutes for provisioning.

### The three API values

**Project Settings → API** (in newer dashboards, **Settings → API Keys**):

| Secret | Labelled | Notes |
|---|---|---|
| `SUPABASE_URL` | Project URL | `https://<ref>.supabase.co` |
| `SUPABASE_ANON_KEY` | `anon` / `public` | Safe in the browser. Row-level security is what protects the data, not this key. |
| `SUPABASE_SERVICE_ROLE_KEY` | `service_role` / `secret` | **Bypasses row-level security.** Never put this in the frontend or in `wrangler.toml` — only in GitHub secrets and `wrangler secret put`. |

Supabase has been migrating to a newer key format (`sb_publishable_…` /
`sb_secret_…`) alongside the legacy JWT-style `anon` / `service_role` keys. If
you see both, either pair works — use publishable wherever this table says
`anon`, and secret wherever it says `service_role`. Do not mix pairs.

### The connection string — read this part

**Settings → Database → Connection string → URI.**

You will be offered more than one. **Take the Session pooler on port 5432**, not
the direct connection.

Why it matters: the direct host (`db.<ref>.supabase.co`) resolves to IPv6 only,
and GitHub Actions runners are IPv4-only. Every scheduled workflow would fail
to connect, and the failure looks like a hang rather than a clear error.

The pooler string looks like:

```
postgresql://postgres.<project-ref>:<password>@aws-0-<region>.pooler.supabase.com:5432/postgres
```

Note the username is `postgres.<project-ref>`, not plain `postgres`. Substitute
the password you saved in step 3.

If you use the **transaction** pooler on port **6543** instead, that also works
— `gamesenze/db.py` detects it and disables asyncpg's prepared-statement cache,
which would otherwise fail partway through a job under concurrency. Session
mode on 5432 is still the simpler choice.

**Check it before going further.** A bad connection string is the single most
common way this setup wastes an afternoon:

```bash
psql "postgresql://postgres.<ref>:<pw>@aws-0-<region>.pooler.supabase.com:5432/postgres" -c "select version();"
```

---

## 2. API-Football — 1 value

`API_FOOTBALL_KEY`

Sign up at **dashboard.api-football.com** → confirm your email → the key is on
the dashboard home, often under **Account** or **My Access**.

⚠️ **Do not sign up through RapidAPI.** Both routes exist and give different
keys. This codebase calls `v3.football.api-sports.io` with an `x-apisports-key`
header, which is the direct api-sports.io route. A RapidAPI key uses a
different host and header pair and will return 403 against this code.

Free tier is 100 requests/day, which is what §3.2 budgets against.

---

## 3. SportsGameOdds — 1 value

`SPORTSGAMEODDS_KEY`

**The key is emailed to you. There is no dashboard showing it**, which is the
usual reason people think signup failed.

1. Go to **sportsgameodds.com/pricing**.
2. Choose the **Amateur** plan — their word for it is "eternally free".
3. Complete checkout. **It asks for a card**, and states it is never charged
   unless you later choose to upgrade. If that is a blocker, see the note below.
4. **Watch your inbox.** The key arrives by email within a couple of minutes.
5. Nothing after a few minutes: check spam, then mail
   **support@sportsgameodds.com**.

Free "Amateur" tier, all of which this codebase is built around:

| Limit | Value | Where it shows up |
|---|---|---|
| Objects/month | 2,500 | §3.3 plans 2,000, leaving a 500 reserve |
| Requests/minute | 10 | Split 6 (Worker) / 3 (fallback) in `config.py` |
| Update frequency | 10 min | Our tightest cadence is 15 min, so we never outpace it |
| Coverage | 8 leagues, 9 bookmakers | Decide your 8 leagues before seeding aliases |

The 10-minute update frequency is worth understanding: on the free plan a price
you fetch may be up to 10 minutes stale at source. Our closest-to-kickoff
window polls every 15 minutes, so we are never asking faster than they refresh
— fetching more often would spend objects to receive the same numbers back.

**If you would rather not enter a card**, the pipeline runs without this key —
you simply get no odds, which means no publishable picks (the gate requires
`odds_fresh`). Everything else works: fixtures, stats, scrapes, the QA layers
and the audit. That is a reasonable way to validate the plumbing first and add
odds when you are ready.

Authentication is the `X-Api-Key` header, which is what
`gamesenze/providers/sgo.py` sends.

## 4. Scraper contact — 1 value

`SCRAPER_CONTACT`

An email address you will actually read, e.g. `data@yourdomain.com`. It goes
into the User-Agent on every scrape:

```
GameSenze/0.1.0 (+data@yourdomain.com)
```

This is REQ-SCRAPE-2. It is publicly visible to FBref, Understat and the rest,
so use a role address rather than your personal one. The point is that a source
who wants to complain or block us can reach us first — do not use a fake
address, and do not use one nobody monitors.

---

## 5. Alerting webhook — 1 value

`ALERT_WEBHOOK_URL`

Optional, strongly recommended. Without it, alerts go only to workflow logs,
which means an unresolved QA flag waits until you happen to look.

**Slack:** api.slack.com/apps → **Create New App** → From scratch → pick your
workspace → **Incoming Webhooks** → toggle on → **Add New Webhook to
Workspace** → choose a channel → copy the URL.

**Discord:** Server Settings → **Integrations** → **Webhooks** → **New Webhook**
→ choose a channel → **Copy Webhook URL**.

Either works. `gamesenze/alerts.py` detects Discord URLs and sends `content`
instead of `text`, because posting the wrong field returns a 400 and the alert
disappears silently.

---

## 6. Netlify — 2 values

`NETLIFY_AUTH_TOKEN`, `NETLIFY_SITE_ID`

1. Sign up at **netlify.com**.
2. **Add new site → Deploy manually.** Drag any empty folder in — we only need
   the site to exist; `deploy-frontend.yml` pushes the real build. Do *not*
   connect it to the GitHub repo, or you will get two competing deploy paths.
3. `NETLIFY_SITE_ID`: **Site configuration → General → Site details → Site ID**
   (a UUID; sometimes labelled "API ID").
4. `NETLIFY_AUTH_TOKEN`: avatar → **User settings → Applications → Personal
   access tokens → New access token**. Copy it now; it is shown once.

Netlify's free tier does not need a card. It asks for one only if you add a
team member or exceed the free bandwidth, neither of which applies here.

---

## 7. GitHub token for the Worker fallback — 1 value

`GH_DISPATCH_TOKEN` (a **Worker** secret, not a GitHub Actions secret)

This is what lets a failing Worker tick fire `worker-fallback.yml` (§8).

GitHub → your avatar → **Settings** → **Developer settings** → **Personal
access tokens** → **Fine-grained tokens** → **Generate new token**:

- **Resource owner:** `xlr8-bl`
- **Repository access:** Only select repositories → `gamesenze`
- **Repository permissions:** **Actions → Read and write**
  (Metadata → Read-only is added automatically; nothing else is needed)
- **Expiration:** set a real date and put a reminder in your calendar. When it
  expires the fallback stops working quietly — the hourly backstop still runs,
  so you lose fast failover, not coverage.

---

## 8. Cloudflare — no value to copy, but it is where the PAT goes

Sign up at **dash.cloudflare.com**. Authentication happens through
`npx wrangler login` in your browser, so there is no Cloudflare token to store.

Cloudflare is the *destination* for four secrets, including the GitHub PAT from
step 7. The Worker needs that PAT because it calls the GitHub API itself when a
tick fails — GitHub Actions secrets are not visible to a Cloudflare Worker, so
it cannot live there.

```bash
cd workers/snapshot
npm install
npx wrangler login                                  # opens a browser

npx wrangler secret put SUPABASE_SERVICE_ROLE_KEY
npx wrangler secret put SPORTSGAMEODDS_KEY
npx wrangler secret put API_FOOTBALL_KEY
npx wrangler secret put GH_DISPATCH_TOKEN           # the PAT from step 7
```

Each prompts for the value and stores it encrypted with Cloudflare. They are
never in the repository and `wrangler secret list` shows only the names.

Then set the one non-secret in `workers/snapshot/wrangler.toml`:

```toml
[vars]
SUPABASE_URL = "https://<your-ref>.supabase.co"
GH_REPO = "xlr8-bl/gamesenze"
```

`SUPABASE_URL` belongs in `[vars]` rather than a secret because it is already
public in the frontend bundle. Never put a real secret there — `wrangler.toml`
is committed.

### Do not deploy until every key is set

`npx wrangler deploy` registers the cron immediately, and the Worker then runs
**every minute**. With a vendor key missing, every tick fails.

Set the secrets now and deploy last. The Worker is the final step of the whole
setup, after the database is migrated and seeded.

You can confirm what is stored without deploying:

```bash
npx wrangler secret list
```

---

## Where each value goes

### GitHub Actions secrets

Repo → **Settings → Secrets and variables → Actions → New repository secret**.
Ten in total:

```
DATABASE_URL                 SUPABASE_URL
SUPABASE_ANON_KEY            SUPABASE_SERVICE_ROLE_KEY
API_FOOTBALL_KEY             SPORTSGAMEODDS_KEY
NETLIFY_AUTH_TOKEN           NETLIFY_SITE_ID
SCRAPER_CONTACT              ALERT_WEBHOOK_URL
```

### Cloudflare Worker secrets

From `workers/snapshot/`:

```bash
npx wrangler login
npx wrangler secret put SUPABASE_SERVICE_ROLE_KEY
npx wrangler secret put SPORTSGAMEODDS_KEY
npx wrangler secret put API_FOOTBALL_KEY
npx wrangler secret put GH_DISPATCH_TOKEN
```

Then edit `workers/snapshot/wrangler.toml` and set `SUPABASE_URL` under
`[vars]`. It belongs there rather than in a secret because it is already public
in the frontend bundle — and putting a genuine secret in `[vars]` would commit
it to the repository.

### Your local `.env`

For running migrations and the seed from your machine:

```bash
cp .env.example .env
```

Fill in `DATABASE_URL`, `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`,
`API_FOOTBALL_KEY`, `SPORTSGAMEODDS_KEY`, `SCRAPER_CONTACT`. `.env` is
gitignored; keep it that way.

Every job entry point loads it automatically (`gamesenze/config.py`), so
`DATABASE_URL` in `.env` is picked up the moment you run `python -m
gamesenze.jobs.migrate` — no `export`/`$env:` needed. Real environment
variables always take priority over `.env`, which is what keeps a
GitHub Actions run safe: the secrets injected via `env:` in a workflow can
never be shadowed by a `.env` file that happens to be sitting in the
checked-out repo.

---

## Verify before proceeding

```bash
# 1. Database reachable, and it is the pooler string
psql "$DATABASE_URL" -c "select current_database(), version();"

# 2. API-Football key valid, and note your remaining quota in the headers
curl -s -D - -o /dev/null \
  -H "x-apisports-key: $API_FOOTBALL_KEY" \
  "https://v3.football.api-sports.io/status" | grep -i "x-ratelimit\|HTTP/"

# 3. SportsGameOdds key valid
curl -s -o /dev/null -w "%{http_code}\n" \
  -H "X-Api-Key: $SPORTSGAMEODDS_KEY" \
  "https://api.sportsgameodds.com/v2/sports"

# 4. Alert webhook reaches you
curl -s -X POST -H "Content-Type: application/json" \
  -d '{"text":"GameSenze setup test","content":"GameSenze setup test"}' \
  "$ALERT_WEBHOOK_URL"
```

Expect `200` from 2 and 3, a message in your channel from 4, and a version
string from 1.

---

## A note on handling these

- Never paste a key into a chat, an issue, or a commit. If one leaks, rotate it
  at the provider rather than deleting the message.
- `SUPABASE_SERVICE_ROLE_KEY` bypasses row-level security entirely. Treat it
  like the database password, because functionally it is one.
- The only key that ever reaches a browser is `SUPABASE_ANON_KEY`, and only via
  `NEXT_PUBLIC_SUPABASE_ANON_KEY` at build time. REQ-BUDGET-2 means no vendor
  key is ever shipped to the client — there is no server in the static export
  that could hold one anyway.
