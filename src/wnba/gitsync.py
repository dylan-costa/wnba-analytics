"""Commit and push new raw data after the daily update."""

import os
import subprocess
from pathlib import Path

from wnba.config import DATA_DIR, REPO_ROOT

RAW_DIR = DATA_DIR / "raw"


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        timeout=120,
        env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},  # fail instead of waiting for a password
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),  # no console flash under pythonw
    )


def _error(result: subprocess.CompletedProcess) -> str:
    lines = (result.stderr or result.stdout).strip().splitlines()
    return lines[-1] if lines else f"exit code {result.returncode}"


def push_raw_data(message: str, *, repo: Path = REPO_ROOT, raw_dir: Path = RAW_DIR, branch: str = "main", remote: str = "origin") -> str:
    """Commit changes under data/raw on `branch` and push them to `remote`.

    Returns a one-line outcome for the update log; never raises, since the
    database update itself already succeeded. Only data/raw is committed, and
    nothing is pushed if the branch has unpushed commits besides data updates,
    so the task never publishes your own work in progress.
    """
    repo, raw_dir = repo.resolve(), raw_dir.resolve()
    if not raw_dir.is_relative_to(repo):
        return "not pushed: data directory is outside the repo"
    raw_path = raw_dir.relative_to(repo).as_posix()

    current = _git(repo, "branch", "--show-current").stdout.strip()
    if current != branch:
        return f"not pushed: {current or 'a detached HEAD'} is checked out, not {branch}"

    committed = False
    if _git(repo, "status", "--porcelain", "--", raw_path).stdout.strip():
        for args in (("add", "--", raw_path), ("commit", "-m", message, "--", raw_path)):
            result = _git(repo, *args)
            if result.returncode != 0:
                return f"not committed: git {args[0]} failed: {_error(result)}"
        committed = True

    ahead = _git(repo, "log", "--format=", "--name-only", f"{remote}/{branch}..HEAD")
    if ahead.returncode != 0:
        return f"{'committed, ' if committed else ''}not pushed: {_error(ahead)}"
    changed_paths = [p for p in ahead.stdout.splitlines() if p]
    if not changed_paths:
        return "no new data"
    if any(not p.startswith(raw_path + "/") for p in changed_paths):
        return f"{'committed, ' if committed else ''}not pushed: {branch} has unpushed commits besides data updates; push manually"

    result = _git(repo, "push", remote, branch)
    if result.returncode != 0:
        return f"{'committed, ' if committed else ''}push failed (will retry next run): {_error(result)}"
    return "committed and pushed" if committed else "pushed earlier data commits"
