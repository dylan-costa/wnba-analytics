"""Commit and push new data after the daily update."""

import os
import subprocess
from pathlib import Path

from wnba.config import DATA_DIR, FORECAST_DIR, REPO_ROOT, SITE_DIR

RAW_DIR = DATA_DIR / "raw"
DATA_DIRS = (RAW_DIR, FORECAST_DIR, SITE_DIR)


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


def push_data(message: str, *, repo: Path = REPO_ROOT, data_dirs=DATA_DIRS, branch: str = "main", remote: str = "origin") -> str:
    """Commit changes under `data_dirs` on `branch` and push them to `remote`.

    Returns a one-line outcome for the update log; never raises, since the
    database update itself already succeeded. Only the data directories are
    committed, and nothing is pushed if the branch has unpushed commits
    touching anything else, so the task never publishes your own work in
    progress.
    """
    repo = repo.resolve()
    paths = []
    for data_dir in data_dirs:
        data_dir = Path(data_dir).resolve()
        if not data_dir.is_relative_to(repo):
            return "not pushed: data directory is outside the repo"
        paths.append(data_dir.relative_to(repo).as_posix())

    current = _git(repo, "branch", "--show-current").stdout.strip()
    if current != branch:
        return f"not pushed: {current or 'a detached HEAD'} is checked out, not {branch}"

    committed = False
    changed = [p for p in paths if _git(repo, "status", "--porcelain", "--", p).stdout.strip()]
    if changed:
        for args in (("add", "--", *changed), ("commit", "-m", message, "--", *changed)):
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
    if any(not any(p.startswith(d + "/") for d in paths) for p in changed_paths):
        return f"{'committed, ' if committed else ''}not pushed: {branch} has unpushed commits besides data updates; push manually"

    result = _git(repo, "push", remote, branch)
    if result.returncode != 0:
        return f"{'committed, ' if committed else ''}push failed (will retry next run): {_error(result)}"
    return "committed and pushed" if committed else "pushed earlier data commits"
