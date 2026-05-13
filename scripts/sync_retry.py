"""
Auto-retry wrapper for evernote-backup sync.

Runs evernote-backup sync in a loop, automatically waiting and retrying
when Evernote's rate limit is hit.

Usage:
    python scripts/sync_retry.py [--dir PATH]

Options:
    --dir   Path to the evernote-backup working directory (default: ./evernote-migration)
"""

import argparse
import re
import subprocess
import sys
import time
from pathlib import Path

_RATE_LIMIT_RE = re.compile(r"Restart program in (\d+):(\d+)")
_BUFFER_SECONDS = 30


def parse_wait_seconds(line: str) -> int | None:
    """
    Extract wait duration in seconds from a rate-limit log line.
    Returns None if the line doesn't contain a rate-limit message.
    """
    match = _RATE_LIMIT_RE.search(line)
    if not match:
        return None
    return int(match.group(1)) * 60 + int(match.group(2))


def _fmt(seconds: int) -> str:
    m, s = divmod(seconds, 60)
    return f"{m}m {s}s" if m else f"{s}s"


def run_sync(work_dir: Path) -> bool:
    """
    Run evernote-backup sync once. Returns True if sync completed successfully.
    Prints output in real time. If rate-limited, waits and returns False.
    """
    process = subprocess.Popen(
        ["evernote-backup", "sync"],
        cwd=work_dir,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )

    wait_seconds = None
    for line in process.stdout:
        print(line, end="", flush=True)
        if wait_seconds is None:
            wait_seconds = parse_wait_seconds(line)

    process.wait()

    if wait_seconds is not None:
        total = wait_seconds + _BUFFER_SECONDS
        print(f"\nRate limit hit — waiting {_fmt(total)} before retrying...\n", flush=True)
        time.sleep(total)
        return False

    return True


def main():
    parser = argparse.ArgumentParser(description="Auto-retry evernote-backup sync on rate limit")
    parser.add_argument(
        "--dir",
        default="evernote-migration",
        help="Working directory for evernote-backup (default: ./evernote-migration)",
    )
    args = parser.parse_args()

    work_dir = Path(args.dir)
    if not work_dir.is_absolute():
        work_dir = Path.cwd() / work_dir

    if not work_dir.exists():
        print(f"Error: directory not found: {work_dir}", file=sys.stderr)
        sys.exit(1)

    attempt = 1
    while True:
        print(f"--- Attempt {attempt} ---", flush=True)
        if run_sync(work_dir):
            print("Synchronization complete.", flush=True)
            break
        attempt += 1


if __name__ == "__main__":
    main()
