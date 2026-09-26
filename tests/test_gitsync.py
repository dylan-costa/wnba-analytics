"""push_data against a throwaway repo with a local bare "remote"."""

import subprocess

import pytest

from wnba.gitsync import push_data


def git(repo, *args):
    return subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=True).stdout.strip()


@pytest.fixture
def repo(tmp_path):
    remote = tmp_path / "remote.git"
    work = tmp_path / "work"
    subprocess.run(["git", "init", "--bare", "-b", "main", str(remote)], check=True, capture_output=True)
    subprocess.run(["git", "init", "-b", "main", str(work)], check=True, capture_output=True)
    git(work, "config", "user.email", "test@example.com")
    git(work, "config", "user.name", "Test")
    git(work, "config", "core.autocrlf", "false")
    (work / "data" / "raw").mkdir(parents=True)
    (work / "data" / "raw" / "2026_regular.csv").write_text("GAME_ID\n1\n")
    (work / "README.md").write_text("readme\n")
    git(work, "add", ".")
    git(work, "commit", "-m", "initial")
    git(work, "remote", "add", "origin", str(remote))
    git(work, "push", "-u", "origin", "main")
    return work


def sync(repo, message="Update data through 2026-09-26"):
    return push_data(message, repo=repo, data_dirs=[repo / "data" / "raw", repo / "data" / "forecasts"])


def remote_log(repo):
    return git(repo, "log", "--format=%s", "origin/main")


def test_nothing_new(repo):
    assert sync(repo) == "no new data"


def test_commits_and_pushes_only_raw_data(repo):
    (repo / "data" / "raw" / "2026_regular.csv").write_text("GAME_ID\n1\n2\n")
    (repo / "data" / "raw" / "2026_playoffs.csv").write_text("GAME_ID\n3\n")
    (repo / "README.md").write_text("work in progress\n")

    assert sync(repo) == "committed and pushed"

    assert remote_log(repo).splitlines()[0] == "Update data through 2026-09-26"
    assert sorted(git(repo, "show", "--format=", "--name-only", "HEAD").splitlines()) == [
        "data/raw/2026_playoffs.csv", "data/raw/2026_regular.csv",
    ]
    assert git(repo, "status", "--porcelain") == "M README.md"  # left alone


def test_skips_other_branches(repo):
    git(repo, "checkout", "-b", "feature")
    (repo / "data" / "raw" / "2026_regular.csv").write_text("GAME_ID\n1\n2\n")
    assert sync(repo) == "not pushed: feature is checked out, not main"
    assert git(repo, "log", "--format=%s") == "initial"


def test_wont_push_your_unpushed_commits(repo):
    (repo / "README.md").write_text("my change\n")
    git(repo, "commit", "-am", "my unpushed work")
    (repo / "data" / "raw" / "2026_regular.csv").write_text("GAME_ID\n1\n2\n")

    result = sync(repo)

    assert result.startswith("committed, not pushed: main has unpushed commits besides data updates")
    assert remote_log(repo) == "initial"


def test_retries_a_failed_push_next_run(repo, tmp_path):
    (repo / "data" / "raw" / "2026_regular.csv").write_text("GAME_ID\n1\n2\n")
    good_url = git(repo, "remote", "get-url", "origin")
    git(repo, "remote", "set-url", "origin", str(tmp_path / "missing.git"))
    assert sync(repo).startswith("committed, push failed (will retry next run)")

    git(repo, "remote", "set-url", "origin", good_url)
    assert sync(repo) == "pushed earlier data commits"
    assert remote_log(repo).splitlines()[0] == "Update data through 2026-09-26"


def test_commits_forecasts_with_raw_data(repo):
    (repo / "data" / "raw" / "2026_regular.csv").write_text("GAME_ID\n1\n2\n")
    (repo / "data" / "forecasts").mkdir()
    (repo / "data" / "forecasts" / "2026_odds.csv").write_text("team,champion\nMIN,0.2\n")

    assert sync(repo) == "committed and pushed"
    assert sorted(git(repo, "show", "--format=", "--name-only", "HEAD").splitlines()) == [
        "data/forecasts/2026_odds.csv", "data/raw/2026_regular.csv",
    ]
