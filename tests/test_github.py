# Copyright 2026 Yauhen Bichel
# SPDX-License-Identifier: Apache-2.0
"""Talking to gh: what it is asked, and what it does with what comes back.

No network and no gh binary: `subprocess.run` is replaced, which also proves the tool never reaches
for a token of its own.
"""
from __future__ import annotations

import json
import subprocess
from typing import Any

import pytest

from homerunner import github
from homerunner.plan import Refused, Repo

REPO = Repo("YauhenBichel", "llm-harness")


class FakeRun:
    """Stands in for subprocess.run, recording the arguments and replaying a prepared answer."""

    def __init__(self, stdout: str = "", stderr: str = "", code: int = 0) -> None:
        self.stdout, self.stderr, self.code = stdout, stderr, code
        self.calls: list[list[str]] = []

    def __call__(self, args: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        self.calls.append(list(args))
        return subprocess.CompletedProcess(args, self.code, self.stdout, self.stderr)


@pytest.fixture(autouse=True)
def gh_exists(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(github.shutil, "which", lambda name: f"/usr/bin/{name}")


def use(monkeypatch: pytest.MonkeyPatch, fake: FakeRun) -> FakeRun:
    monkeypatch.setattr(github.subprocess, "run", fake)
    return fake


def test_facts_are_read_from_gh(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = use(monkeypatch, FakeRun(json.dumps(
        {"private": True, "archived": False, "admin": True, "fork": False})))
    facts = github.facts(REPO)
    assert facts.private and facts.admin and not facts.archived
    assert fake.calls[0][:3] == ["gh", "api", "repos/YauhenBichel/llm-harness"]


def test_a_missing_field_is_read_as_false_not_as_permission(monkeypatch: pytest.MonkeyPatch) -> None:
    """If GitHub does not say you are an admin, you are not one."""
    use(monkeypatch, FakeRun(json.dumps({"private": True})))
    facts = github.facts(REPO)
    assert facts.admin is False


def test_the_registration_token_is_asked_for_but_never_returned_from_a_call_that_stores_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = use(monkeypatch, FakeRun("tok_abc123\n"))
    assert github.registration_token(REPO) == "tok_abc123"
    assert fake.calls[0][2] == "-X" and fake.calls[0][3] == "POST"
    assert "registration-token" in fake.calls[0][4]


def test_an_empty_token_is_refused_rather_than_passed_on(monkeypatch: pytest.MonkeyPatch) -> None:
    use(monkeypatch, FakeRun("\n"))
    with pytest.raises(Refused, match="did not return a registration token"):
        github.registration_token(REPO)


def test_not_signed_in_says_what_to_run(monkeypatch: pytest.MonkeyPatch) -> None:
    use(monkeypatch, FakeRun(stderr="gh: To get started with GitHub CLI, please run: gh auth login",
                             code=1))
    with pytest.raises(Refused, match="gh auth login"):
        github.facts(REPO)


def test_a_gh_failure_keeps_its_own_message(monkeypatch: pytest.MonkeyPatch) -> None:
    use(monkeypatch, FakeRun(stderr="HTTP 404: Not Found", code=1))
    with pytest.raises(Refused, match="404"):
        github.facts(REPO)


def test_a_missing_gh_says_where_to_get_it(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(github.shutil, "which", lambda name: None)
    with pytest.raises(Refused, match="cli.github.com"):
        github.facts(REPO)


def test_signed_in_as_returns_none_rather_than_raising(monkeypatch: pytest.MonkeyPatch) -> None:
    """`doctor` reports on this; it must not blow up when gh is unhappy."""
    use(monkeypatch, FakeRun(stderr="nope", code=1))
    assert github.signed_in_as() is None


def test_runners_of_a_repository_are_listed(monkeypatch: pytest.MonkeyPatch) -> None:
    use(monkeypatch, FakeRun(json.dumps([{"name": "yserver", "status": "online",
                                          "labels": ["self-hosted", "yserver"]}])))
    found = github.runners(REPO)
    assert found[0]["status"] == "online"


def test_no_runners_is_an_empty_list_not_an_error(monkeypatch: pytest.MonkeyPatch) -> None:
    use(monkeypatch, FakeRun("[]"))
    assert github.runners(REPO) == []
