"""Entry points. Each module is runnable as `python -m gamesenze.jobs.<name>`.

Split by where they run: the jobs here are the GitHub Actions half of §2.2 —
heavy but flexible, timing does not matter. Anything time-critical is in
workers/snapshot.
"""
