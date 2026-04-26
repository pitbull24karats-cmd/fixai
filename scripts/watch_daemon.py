#!/usr/bin/env python3
"""
watch_daemon.py — watchdog daemon for FixAI
Monitors ~/jarvis_server and ~/Desktop/Jarvis, calls /watch/trigger on change.
Managed by launchd: com.fixai.watch.plist
"""

import logging
import sys
import time
from pathlib import Path

import httpx
from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

FIXAI_URL = "http://localhost:8005"
WATCH_DIRS = [
    Path.home() / "jarvis_server",
    Path.home() / "Desktop" / "Jarvis",
]
IGNORED_DIRS = {".git", "__pycache__", ".venv", "venv", "node_modules", ".mypy_cache"}
WATCHED_EXTS = {".py", ".js", ".ts", ".jsx", ".tsx", ".go", ".rb", ".java", ".sh", ".yaml", ".yml", ".json"}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [watch_daemon] %(levelname)s %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)


def _register(path: str) -> None:
    try:
        r = httpx.post(f"{FIXAI_URL}/watch/register", json={"path": path}, timeout=5)
        if r.status_code < 300:
            log.info("registered: %s", path)
        else:
            log.warning("register failed (%d): %s", r.status_code, path)
    except Exception as e:
        log.error("register error: %s", e)


def _trigger(path: str) -> None:
    try:
        r = httpx.post(f"{FIXAI_URL}/watch/trigger", json={"path": path}, timeout=60)
        log.info("trigger %d: %s", r.status_code, path)
    except Exception as e:
        log.error("trigger error: %s", e)


class FixAIHandler(FileSystemEventHandler):
    def _should_handle(self, event: FileSystemEvent) -> bool:
        if event.is_directory:
            return False
        p = Path(event.src_path)
        if p.suffix not in WATCHED_EXTS:
            return False
        if any(part in IGNORED_DIRS for part in p.parts):
            return False
        return True

    def on_modified(self, event: FileSystemEvent) -> None:
        if self._should_handle(event):
            log.info("modified: %s", event.src_path)
            _trigger(event.src_path)

    def on_created(self, event: FileSystemEvent) -> None:
        if self._should_handle(event):
            log.info("created: %s", event.src_path)
            _trigger(event.src_path)


def main() -> None:
    handler = FixAIHandler()
    observer = Observer()

    for watch_dir in WATCH_DIRS:
        if watch_dir.exists():
            _register(str(watch_dir))
            observer.schedule(handler, str(watch_dir), recursive=True)
            log.info("watching: %s", watch_dir)
        else:
            log.warning("directory not found, skipping: %s", watch_dir)

    observer.start()
    log.info("FixAI watch daemon started")
    try:
        while True:
            time.sleep(5)
    except KeyboardInterrupt:
        pass
    finally:
        observer.stop()
        observer.join()
        log.info("FixAI watch daemon stopped")


if __name__ == "__main__":
    main()
