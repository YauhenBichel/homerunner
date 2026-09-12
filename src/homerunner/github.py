# Copyright 2026 Yauhen Bichel
# SPDX-License-Identifier: Apache-2.0
"""Talking to GitHub through the `gh` command, on purpose.

homerunner stores no token and asks for none. Everything that needs credentials is asked of `gh`,
which you have already signed in, and the registration token it fetches lives for an hour and never
touches the disk. That is the whole security design: the tool has nothing worth stealing.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from typing import Any

from .plan import Refused, Repo, RepoFacts


def _gh(args: list[str], input_text: str | None = None) -> str:
    if shutil.which("gh") is None:
        raise Refused("the GitHub CLI (gh) is not installed: https://cli.github.com")
    try:
        done = subprocess.run(["gh", *args], capture_output=True, text=True, input=input_text,
                              timeout=120, check=False)
    except subprocess.TimeoutExpired as exc:
        raise Refused(f"gh {' '.join(args[:2])} timed out") from exc
    if done.returncode != 0:
        message = (done.stderr or done.stdout).strip().splitlines()
        detail = message[-1] if message else f"exit {done.returncode}"
        if "authentication" in detail.lower() or "gh auth login" in detail.lower():
            raise Refused("gh is not signed in: run `gh auth login`")
        raise Refused(f"gh {' '.join(args[:2])} failed: {detail}")
    return done.stdout


def signed_in_as() -> str | None:
    try:
        return json.loads(_gh(["api", "user", "--jq", "{login: .login}"]))["login"]
    except (Refused, json.JSONDecodeError, KeyError):
        return None


def facts(repo: Repo) -> RepoFacts:
    """What GitHub says about the repository, reduced to what decides anything."""
    raw = _gh(["api", f"repos/{repo.slug}",
               "--jq", "{private: .private, archived: .archived, admin: .permissions.admin, fork: .fork}"])
    data: dict[str, Any] = json.loads(raw)
    return RepoFacts(private=bool(data.get("private")), archived=bool(data.get("archived")),
                     admin=bool(data.get("admin")), fork=bool(data.get("fork")))


def registration_token(repo: Repo) -> str:
    """A one-hour token for adding a runner. Passed straight to config.sh; never written down."""
    raw = _gh(["api", "-X", "POST", f"repos/{repo.slug}/actions/runners/registration-token",
               "--jq", ".token"])
    token = raw.strip()
    if not token:
        raise Refused(f"GitHub did not return a registration token for {repo.slug}")
    return token


def removal_token(repo: Repo) -> str:
    raw = _gh(["api", "-X", "POST", f"repos/{repo.slug}/actions/runners/remove-token", "--jq", ".token"])
    return raw.strip()


def runners(repo: Repo) -> list[dict[str, Any]]:
    raw = _gh(["api", f"repos/{repo.slug}/actions/runners",
               "--jq", "[.runners[] | {name: .name, status: .status, labels: [.labels[].name]}]"])
    found = json.loads(raw or "[]")
    return found if isinstance(found, list) else []


def latest_runner_version() -> str:
    raw = _gh(["api", "repos/actions/runner/releases/latest", "--jq", ".tag_name"])
    return raw.strip().lstrip("v")
