#!/usr/bin/env python3
import asyncio
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).parent.parent))
from services.analyzer import analyze_for_issues

LOG_PATH = Path.home() / "Desktop" / "fixai" / "logs" / "daily_scan.log"
DEVBRAIN_INGEST = "http://localhost:8003/ingest"
SCAN_TARGETS = [
    Path.home() / "jarvis_server",
    Path.home() / "Desktop" / "Jarvis",
    Path.home() / "Desktop" / "devbrain",
    Path.home() / "Desktop" / "fixai",
]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(LOG_PATH, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger(__name__)


def collect_target_files() -> list[Path]:
    exts = {".py", ".swift"}
    files = []
    for base in SCAN_TARGETS:
        if not base.exists():
            log.warning("Target not found, skipping: %s", base)
            continue
        found = sorted(f for f in base.rglob("*") if f.is_file() and f.suffix in exts)
        log.info("Found %d files in %s", len(found), base)
        files.extend(found)
    return files


def read_truncated(path: Path, max_lines: int = 100, max_bytes: int = 3000) -> str:
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        text = "\n".join(lines[:max_lines])
        return text[:max_bytes]
    except Exception as e:
        return f"[read error: {e}]"


async def ingest_to_devbrain(client: httpx.AsyncClient, file: Path, issues: dict, summary: dict) -> None:
    payload = {
        "source": "fixai_daily_scan",
        "file": str(file),
        "issues": issues,
        "summary": summary,
        "scanned_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        resp = await client.post(DEVBRAIN_INGEST, json=payload, timeout=15.0)
        resp.raise_for_status()
        log.info("Ingested %s → devbrain (status %d)", file.name, resp.status_code)
    except Exception as e:
        log.warning("Ingest failed for %s: %s", file.name, e)


async def scan_all() -> None:
    files = collect_target_files()
    if not files:
        log.warning("No .py or .swift files found in any target directory.")
        return

    log.info("=== daily_scan start: %d files ===", len(files))
    ok = error = 0

    async with httpx.AsyncClient() as client:
        for f in files:
            log.info("Scanning %s", f)
            content = read_truncated(f)
            try:
                issues = await analyze_for_issues(f, content)
                total = sum(len(v) for v in issues.values() if isinstance(v, list))
                summary = {
                    "total": total,
                    "high": sum(
                        1 for cat in issues.values() if isinstance(cat, list)
                        for item in cat if isinstance(item, dict) and item.get("severity") == "high"
                    ),
                    "medium": sum(
                        1 for cat in issues.values() if isinstance(cat, list)
                        for item in cat if isinstance(item, dict) and item.get("severity") == "medium"
                    ),
                    "low": sum(
                        1 for cat in issues.values() if isinstance(cat, list)
                        for item in cat if isinstance(item, dict) and item.get("severity") == "low"
                    ),
                }
                log.info("  → %d issues (H:%d M:%d L:%d)", total, summary["high"], summary["medium"], summary["low"])
                await ingest_to_devbrain(client, f, issues, summary)
                ok += 1
            except Exception as e:
                log.error("Failed to scan %s: %s", f, e)
                error += 1

    log.info("=== daily_scan done: %d ok, %d errors ===", ok, error)


if __name__ == "__main__":
    asyncio.run(scan_all())
