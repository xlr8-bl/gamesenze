# Migrations

Applied in filename order. They are idempotent (`create ... if not exists`,
`create or replace view`), so re-running the directory against an existing
database is safe.

```bash
python -m gamesenze.jobs.migrate            # applies anything unapplied
python -m gamesenze.jobs.migrate --dry-run  # shows what would run
```

Order matters for one reason beyond dependencies: `0002_qa.sql` deploys the
supervision tables, and nothing should ingest before it exists. Build the QA
layer before the analysis layer (§11).
