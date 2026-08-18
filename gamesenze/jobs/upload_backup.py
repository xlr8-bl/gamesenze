"""Push a verified dump to Supabase Storage — §9.2.

Runs only after verify_restore has passed, so what lands in Storage is a backup
we have actually restored rather than a file we hope is one.
"""

from __future__ import annotations

import os
import sys
import urllib.request
from pathlib import Path

BUCKET = "backups"
KEEP = 8  # roughly two months of weekly dumps


def upload(path: Path, supabase_url: str, key: str) -> None:
    target = f"{supabase_url}/storage/v1/object/{BUCKET}/{path.name}"
    request = urllib.request.Request(
        target,
        data=path.read_bytes(),
        method="POST",
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/octet-stream",
            "x-upsert": "true",
        },
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        if response.status >= 300:
            raise RuntimeError(f"upload failed: {response.status}")
    print(f"uploaded {path.name} ({path.stat().st_size / 1e6:.1f}MB)")


def main() -> None:
    directory = Path(sys.argv[1] if len(sys.argv) > 1 else "backup")
    supabase_url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    if not supabase_url or not key:
        print("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required",
              file=sys.stderr)
        raise SystemExit(2)

    dumps = sorted(directory.glob("*.dump"))
    if not dumps:
        print(f"no dumps in {directory}", file=sys.stderr)
        raise SystemExit(1)

    for dump in dumps:
        upload(dump, supabase_url, key)
    print(f"retention: keep the most recent {KEEP} objects in {BUCKET}/")
    raise SystemExit(0)


if __name__ == "__main__":
    main()
