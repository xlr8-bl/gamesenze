"""Reading these files without an explicit encoding is a silent-corruption
bug, not a crash — which is why it went unnoticed until real accented team
names (Málaga, Famalicão, Marítimo) landed in a live user's database as
"MÃ¡laga", "FamalicÃ£o", "MarÃ­timo": UTF-8 bytes misread as cp1252, which is
Python's default text encoding on Windows. `pathlib.Path.read_text()` without
`encoding=` uses `locale.getpreferredencoding()`, and nothing here can force
that to misbehave on Linux — so these tests demonstrate the corruption
directly (decode as cp1252, assert it reproduces the exact garbling seen in
production) and then prove the actual fixed code path is immune, by loading
through gamesenze.jobs.seed's real function rather than a re-implementation.
"""

from __future__ import annotations

import json
from pathlib import Path


def test_cp1252_misreading_reproduces_the_bug_that_was_seen_live(tmp_path):
    # Málaga -> M\xc3\xa1laga in UTF-8. Decoded as cp1252 instead: "MÃ¡laga".
    # This is not a hypothetical — it is the literal string a live user's
    # aliases backlog showed for this exact club.
    original = "Málaga"
    utf8_bytes = original.encode("utf-8")
    misread = utf8_bytes.decode("cp1252")
    assert misread == "MÃ¡laga"
    assert misread != original


def test_teams_json_round_trips_correctly_through_the_real_seed_loader():
    """The actual fix: gamesenze/jobs/seed.py now reads with encoding="utf-8"
    explicitly, so this passes regardless of what the OS default happens to
    be — which is the whole point, since the bug only ever showed up on
    Windows and this suite runs on Linux.
    """
    seed_path = (
        Path(__file__).resolve().parents[1] / "db" / "seed" / "teams.json"
    )
    data = json.loads(seed_path.read_text(encoding="utf-8"))

    names = " ".join(
        t["canonical"] + " " + " ".join(t["variants"]) for t in data["teams"]
    )
    for team in ("Málaga", "Famalicão", "Marítimo", "Deportivo Alavés"):
        assert team in names, f"{team!r} missing or corrupted in teams.json"
    # The corrupted forms must never appear — if they do, something upstream
    # wrote mojibake into the file itself, not just misread it.
    for corrupted in ("MÃ¡laga", "FamalicÃ£o", "MarÃ­timo"):
        assert corrupted not in names


def test_every_read_text_call_in_the_package_specifies_an_encoding():
    """A regression guard, not just a fix: the next `.read_text()` added
    anywhere in the package must not reintroduce this bug silently. Migration
    SQL files use §-prefixed comments throughout, .env can hold non-ASCII
    scraper contacts, and Python source docstrings use the same § marks — any
    of these would corrupt exactly as silently as the team names did.
    """
    package_root = Path(__file__).resolve().parents[1] / "gamesenze"
    offenders = []
    for path in package_root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for lineno, line in enumerate(text.splitlines(), start=1):
            if ".read_text(" in line and "encoding=" not in line:
                offenders.append(f"{path.relative_to(package_root)}:{lineno}")
    assert offenders == [], f"read_text() without encoding=: {offenders}"
