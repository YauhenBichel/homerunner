# Copyright 2026 Yauhen Bichel
# SPDX-License-Identifier: Apache-2.0
"""The decisions. The first test is the reason this tool exists."""
from __future__ import annotations

from pathlib import Path

import pytest

from homerunner.plan import (
    Refused,
    Repo,
    RepoFacts,
    check_allowed,
    labels,
    parse_repo,
    runner_asset,
    runner_dir,
    supports_services,
    unit_name,
    unit_text,
)

PRIVATE = RepoFacts(private=True, archived=False, admin=True)


def test_a_public_repository_is_refused() -> None:
    """A self-hosted runner on a public repository executes code from anyone's pull request, on
    this machine. That is the mistake this tool exists to prevent, so it is the first test."""
    repo = Repo("YauhenBichel", "moe-fit")
    with pytest.raises(Refused) as exc:
        check_allowed(repo, RepoFacts(private=False, archived=False, admin=True))
    message = str(exc.value)
    assert "public" in message
    assert "anyone's pull request" in message, "say what actually goes wrong, not just 'refused'"
    assert "--i-know-this-is-public" in message, "and how to override it deliberately"


def test_the_public_override_is_honoured_when_asked_for_explicitly() -> None:
    check_allowed(Repo("o", "r"), RepoFacts(private=False, archived=False, admin=True),
                  force_public=True)


def test_a_private_repository_is_allowed() -> None:
    check_allowed(Repo("o", "r"), PRIVATE)


def test_an_archived_repository_is_refused() -> None:
    with pytest.raises(Refused, match="archived"):
        check_allowed(Repo("o", "r"), RepoFacts(private=True, archived=True, admin=True))


def test_without_admin_it_is_refused_before_anything_is_downloaded() -> None:
    with pytest.raises(Refused, match="admin"):
        check_allowed(Repo("o", "r"), RepoFacts(private=True, archived=False, admin=False))


@pytest.mark.parametrize("text", [
    "YauhenBichel/moe-fit",
    "https://github.com/YauhenBichel/moe-fit",
    "https://github.com/YauhenBichel/moe-fit.git",
    "  YauhenBichel/moe-fit  ",
])
def test_a_repository_can_be_named_the_ways_people_paste_it(text: str) -> None:
    assert parse_repo(text) == Repo("YauhenBichel", "moe-fit")


@pytest.mark.parametrize("text", ["", "no-slash", "/leading", "trailing/", "a/b/c", "a b/c"])
def test_nonsense_names_are_refused(text: str) -> None:
    with pytest.raises(Refused):
        parse_repo(text)


def test_one_service_per_repository_named_after_it() -> None:
    assert unit_name(Repo("YauhenBichel", "llm-harness")) == "homerunner-yauhenbichel-llm-harness"


def test_two_repositories_of_the_same_name_do_not_collide() -> None:
    """Different owners, same repository name: the directories and services must stay apart."""
    root = Path("/tmp/runners")
    mine, theirs = Repo("me", "ci"), Repo("you", "ci")
    assert runner_dir(root, mine) != runner_dir(root, theirs)
    assert unit_name(mine) != unit_name(theirs)


def test_the_host_label_is_what_a_workflow_targets() -> None:
    assert labels(host="yserver") == ["yserver"]
    assert labels(["gpu", "GPU", " "], host="yserver") == ["yserver", "gpu"]


def test_the_unit_yields_to_whatever_the_machine_is_for() -> None:
    text = unit_text(Repo("o", "r"), Path("/home/me/runner"))
    assert "Nice=15" in text
    assert "IOSchedulingClass=idle" in text
    assert "KillMode=process" in text, "a job in flight should finish, not be killed mid-write"
    assert "WantedBy=default.target" in text, "a user service, so no root is needed"


def test_the_service_starts_runsvc_not_run_sh() -> None:
    """run.sh leaves the listener running when systemd stops the unit; the orphan keeps the
    registration and the next start collides with it ("A session for this runner already exists"),
    leaving the runner offline while jobs queue. runsvc.sh forwards the signal."""
    text = unit_text(Repo("o", "r"), Path("/home/me/runner"))
    assert "ExecStart=/home/me/runner/bin/runsvc.sh" in text
    assert "/run.sh" not in text


def test_an_ephemeral_runner_is_not_restarted() -> None:
    """It exits after one job on purpose; restarting it would fight the design."""
    text = unit_text(Repo("o", "r"), Path("/run"), ephemeral=True)
    assert "Restart=no" in text
    assert "Ephemeral" in text


def test_a_long_running_runner_is_restarted() -> None:
    assert "Restart=always" in unit_text(Repo("o", "r"), Path("/run"))


@pytest.mark.parametrize(("system", "machine_name", "expected"), [
    ("linux", "x86_64", "actions-runner-linux-x64-2.337.0.tar.gz"),
    ("linux", "aarch64", "actions-runner-linux-arm64-2.337.0.tar.gz"),
    ("darwin", "arm64", "actions-runner-osx-arm64-2.337.0.tar.gz"),
])
def test_the_right_release_asset_per_platform(system: str, machine_name: str, expected: str) -> None:
    assert runner_asset("v2.337.0", system, machine_name) == expected
    assert runner_asset("2.337.0", system, machine_name) == expected, "with or without the v"


def test_an_unsupported_platform_is_refused_by_name() -> None:
    with pytest.raises(Refused, match="windows"):
        runner_asset("2.337.0", "windows", "x86_64")


def test_only_linux_can_keep_a_runner_alive_today() -> None:
    """macOS would need launchd. Saying so is better than pretending it works."""
    assert supports_services("linux")
    assert not supports_services("darwin")
