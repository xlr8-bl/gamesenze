"""Download the resolved crests and artwork into the site's own asset folder.

Why local rather than hotlinked
-------------------------------
The manifest holds URLs on someone else's CDN. Pointing the site at them means
every page load depends on a third party staying up, staying fast, and not
deciding one morning that it would rather not serve us. It also means a
restricted network renders a page full of broken images, which we found out by
running the site behind one.

So the crest of every club we cover, and one photograph per competition, get
pulled once and committed. Crests are the expensive case for a CDN and the
cheap case for a repository: 156 files at a few kilobytes each, on every row of
every board. Photography is the reverse, so only one frame per competition
comes down, resized and re-encoded rather than shipped at source resolution.

    python -m gamesenze.jobs.fetch_media           # fetch what is missing
    python -m gamesenze.jobs.fetch_media --refresh # re-fetch everything
"""

from __future__ import annotations

import argparse
import asyncio
import io
import json
import re
import sys
from pathlib import Path

import httpx
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
MEDIA_FILE = ROOT / "db" / "seed" / "media.json"
OUT = ROOT / "web" / "public" / "media"
INDEX = ROOT / "web" / "lib" / "media-local.json"

CREST_PX = 128       # rendered at 64 at most, so 128 covers 2x displays
PHOTO_W = 1600       # a full-bleed hero on a large screen
PHOTO_QUALITY = 74


def slug(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", name.lower().strip())
    return s.strip("-")


async def fetch(client: httpx.AsyncClient, url: str) -> bytes | None:
    for attempt in range(4):
        try:
            r = await client.get(url, timeout=40.0)
            if r.status_code == 404:
                return None
            r.raise_for_status()
            return r.content
        except httpx.HTTPError:
            if attempt == 3:
                return None
            await asyncio.sleep(2 ** attempt)
    return None


def save_crest(raw: bytes, path: Path) -> int:
    """Fit inside a square, keeping transparency and the aspect ratio."""
    img = Image.open(io.BytesIO(raw)).convert("RGBA")
    img.thumbnail((CREST_PX, CREST_PX), Image.LANCZOS)
    canvas = Image.new("RGBA", (CREST_PX, CREST_PX), (0, 0, 0, 0))
    canvas.paste(img, ((CREST_PX - img.width) // 2, (CREST_PX - img.height) // 2))
    canvas.save(path, "WEBP", quality=88, method=6)
    return path.stat().st_size


def save_photo(raw: bytes, path: Path) -> int:
    img = Image.open(io.BytesIO(raw)).convert("RGB")
    if img.width > PHOTO_W:
        img = img.resize((PHOTO_W, round(img.height * PHOTO_W / img.width)), Image.LANCZOS)
    img.save(path, "WEBP", quality=PHOTO_QUALITY, method=6)
    return path.stat().st_size


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()

    manifest = json.loads(MEDIA_FILE.read_text(encoding="utf-8"))
    (OUT / "crests").mkdir(parents=True, exist_ok=True)
    (OUT / "photos").mkdir(parents=True, exist_ok=True)

    index: dict[str, dict[str, str]] = {"crests": {}, "competitions": {}}
    total = 0

    async with httpx.AsyncClient(headers={"user-agent": "gamesenze/1.0"}) as client:
        teams = manifest.get("teams", {})
        print(f"crests: {len(teams)}", flush=True)
        for i, (name, row) in enumerate(sorted(teams.items()), 1):
            url = row.get("badge")
            if not url:
                continue
            path = OUT / "crests" / f"{slug(name)}.webp"
            if path.exists() and not args.refresh:
                index["crests"][name] = f"/media/crests/{path.name}"
                total += path.stat().st_size
                continue
            raw = await fetch(client, url)
            if not raw:
                print(f"  missed {name}", flush=True)
                continue
            try:
                total += save_crest(raw, path)
            except OSError as exc:
                print(f"  bad image for {name}: {exc}", flush=True)
                continue
            index["crests"][name] = f"/media/crests/{path.name}"
            if i % 40 == 0:
                print(f"  {i}/{len(teams)}", flush=True)

        comps = manifest.get("competitions", {})
        print(f"competition artwork: {len(comps)}", flush=True)
        for key, row in sorted(comps.items()):
            entry: dict[str, str] = {}

            badge = row.get("badge")
            if badge:
                path = OUT / "crests" / f"comp-{key}.webp"
                if path.exists() and not args.refresh:
                    entry["badge"] = f"/media/crests/{path.name}"
                    total += path.stat().st_size
                else:
                    raw = await fetch(client, badge)
                    if raw:
                        try:
                            total += save_crest(raw, path)
                            entry["badge"] = f"/media/crests/{path.name}"
                        except OSError:
                            pass

            # One frame per competition. Four would look no better on a page
            # that shows one at a time, and would quadruple what we carry.
            photo = (row.get("fanart") or [None])[0] or row.get("banner")
            if photo:
                path = OUT / "photos" / f"{key}.webp"
                if path.exists() and not args.refresh:
                    entry["photo"] = f"/media/photos/{path.name}"
                    total += path.stat().st_size
                else:
                    raw = await fetch(client, photo)
                    if raw:
                        try:
                            total += save_photo(raw, path)
                            entry["photo"] = f"/media/photos/{path.name}"
                        except OSError:
                            pass

            if entry:
                index["competitions"][key] = entry
            print(f"  {key}: {', '.join(entry) or 'nothing'}", flush=True)

    INDEX.write_text(json.dumps(index, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(
        f"\n{len(index['crests'])} crests, {len(index['competitions'])} competitions, "
        f"{total / 1_048_576:.1f} MB on disk"
    )
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
