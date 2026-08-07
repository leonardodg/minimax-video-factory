#!/usr/bin/env python3
"""Fail if a personal home-directory path is committed to the repository.

This repo is public and publishes a documentation site. An absolute path like
`/home/<user>/...` leaks the maintainer's username and machine layout to every
reader, and it is useless to anyone else — nobody else has that directory.

Committed files should use, in order of preference:
  - a path relative to the repo, or one derived from the script's own location
  - `$PROJECT_ROOT` / `${PROJECT_ROOT}` for project-rooted paths in docs
  - `$HOME` for paths genuinely under a user's home

Run:  uv run --project . python tests/unit_privacy.py
Exit 0 = all pass.
"""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Any absolute path into a user's home directory, on Linux or macOS.
HOME_PATH = re.compile(r"/(?:home|Users)/[A-Za-z0-9._-]+/")

# Extensions worth scanning: text a human or a machine will read.
SCANNED_SUFFIXES = {
    ".md", ".py", ".sh", ".yml", ".yaml", ".json", ".toml", ".example", ".cfg", ".ini",
}

# Files where a home path is the subject matter rather than a leak.
ALLOWED = {
    "tests/unit_privacy.py",  # this file documents the pattern it forbids
}

FAIL = 0


def ok(label: str) -> None:
    print(f"  [ok]   {label}")


def bad(label: str) -> None:
    global FAIL
    FAIL += 1
    print(f"  [BAD]  {label}")


def tracked_files() -> list[Path]:
    """Only files git actually tracks — ignore .venv, site/, worktrees, caches."""
    out = subprocess.run(
        ["git", "-C", str(ROOT), "ls-files"],
        capture_output=True, text=True, check=True,
    )
    return [ROOT / line for line in out.stdout.splitlines() if line]


print("== unit_privacy: no home-directory paths in tracked files ==")

offenders: list[str] = []
scanned = 0
for path in tracked_files():
    rel = path.relative_to(ROOT).as_posix()
    if rel in ALLOWED or path.suffix not in SCANNED_SUFFIXES or not path.is_file():
        continue
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        continue
    scanned += 1
    for lineno, line in enumerate(text.splitlines(), start=1):
        match = HOME_PATH.search(line)
        if match:
            offenders.append(f"{rel}:{lineno}: {line.strip()[:100]}")

if not offenders:
    ok(f"scanned {scanned} tracked files, no home-directory paths")
else:
    bad(
        f"{len(offenders)} home-directory path(s) committed — this repo is public:"
    )
    for entry in offenders:
        print(f"           {entry}")
    print(
        "\n           Use a repo-relative path, $PROJECT_ROOT, or $HOME instead."
    )

print()
if FAIL:
    print(f"FAIL: {FAIL}")
    sys.exit(1)
print("ALL PASS")
