# Copyright 2026 Yauhen Bichel
# SPDX-License-Identifier: Apache-2.0
"""The decisions, with nothing that touches the machine.

Everything here is a pure function of what GitHub said and what you asked for, so the rules that
matter - above all, refusing a public repository - can be tested without a runner, a token or a
network.
"""
from __future__ import annotations

import re
import socket
from dataclasses import dataclass
from pathlib import Path

REPO = re.compile(r"^(?P<owner>[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})?)/(?P<name>[A-Za-z0-9._-]{1,100})$")

# CI must never outrank what the machine is actually for. These are the two knobs that decide it,
# and they are the reason a runner at home is tolerable at all: a test run yields to everything.
DEFAULT_NICE = 15
DEFAULT_IO_CLASS = "idle"


class Refused(Exception):
    """The thing you asked for is not safe or not possible, with the reason said plainly."""


@dataclass(frozen=True)
class Repo:
    owner: str
    name: str

    @property
    def slug(self) -> str:
        return f"{self.owner}/{self.name}"

    @property
    def url(self) -> str:
        return f"https://github.com/{self.slug}"


def parse_repo(text: str) -> Repo:
    text = text.strip().removeprefix("https://github.com/").removesuffix(".git").strip("/")
    match = REPO.match(text)
    if not match:
        raise Refused(f"'{text}' is not an owner/repository name")
    return Repo(match.group("owner"), match.group("name"))


@dataclass(frozen=True)
class RepoFacts:
    """What GitHub says about a repository; only the parts that decide anything."""

    private: bool
    archived: bool
    admin: bool
    fork: bool = False


def check_allowed(repo: Repo, facts: RepoFacts, force_public: bool = False) -> None:
    """Refuse the combinations that end badly. The first one is the whole point of this tool.

    A self-hosted runner on a **public** repository will execute code from a pull request opened by
    anyone, on the machine it runs on - your machine, with your keys, your models and your home
    directory. GitHub documents it; people discover it anyway. So this refuses by default, and the
    override is deliberately ugly to type.
    """
    if not facts.private and not force_public:
        raise Refused(
            f"{repo.slug} is public. A self-hosted runner on a public repository runs code from "
            f"anyone's pull request on this machine, with your files and your keys. Use a hosted "
            f"runner, or pass --i-know-this-is-public if this machine is disposable."
        )
    if facts.archived:
        raise Refused(f"{repo.slug} is archived; nothing will ever run")
    if not facts.admin:
        raise Refused(f"you need admin on {repo.slug} to register a runner for it")


def unit_name(repo: Repo) -> str:
    """One service per repository, named so `systemctl --user` output is readable."""
    return f"homerunner-{repo.owner}-{repo.name}".lower()


def runner_dir(root: Path, repo: Repo) -> Path:
    return root / f"{repo.owner}-{repo.name}".lower()


def labels(extra: list[str] | None = None, host: str | None = None) -> list[str]:
    """`self-hosted` is added by GitHub; the host name is what a workflow should actually target."""
    found = [host or socket.gethostname().split(".")[0].lower()]
    for label in extra or []:
        cleaned = label.strip().lower()
        if cleaned and cleaned not in found:
            found.append(cleaned)
    return found


def unit_text(repo: Repo, directory: Path, nice: int = DEFAULT_NICE,
              io_class: str = DEFAULT_IO_CLASS, ephemeral: bool = False) -> str:
    """The systemd user service. A user service needs no root and stops when the machine does.

    It starts `bin/runsvc.sh`, not `run.sh`. Measured the hard way on 2026-09-12: with `run.sh`,
    `systemctl --user stop` left the listener running, because `KillMode=process` signals only the
    main process and `run.sh` drops its signal trap in the self-update branch. The orphan then held
    the registration, so the next start met "A session for this runner already exists" and the
    runner sat offline while jobs queued. `runsvc.sh` traps TERM and forwards it to the service it
    started, which is why GitHub's own installer uses it.
    """
    restart = "no" if ephemeral else "always"
    note = ("# Ephemeral: the runner takes one job and exits, and homerunner registers a fresh one.\n"
            if ephemeral else "")
    return f"""[Unit]
Description=GitHub Actions runner for {repo.slug} (homerunner)
Documentation={repo.url}/settings/actions/runners
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory={directory}
ExecStart={directory}/bin/runsvc.sh
{note}Restart={restart}
RestartSec=5
# A job may be running; let it finish rather than killing the whole process group.
KillMode=process
KillSignal=SIGTERM
TimeoutStopSec=5min
# CI yields to whatever this machine is really for.
Nice={nice}
IOSchedulingClass={io_class}
# The runner needs the home directory it was configured in, and nothing above it.
PrivateTmp=true
NoNewPrivileges=true

[Install]
WantedBy=default.target
"""


def runner_asset(version: str, system: str, machine: str) -> str:
    """The release asset for this platform, or a refusal naming what is supported."""
    plain = version.lstrip("v")
    if system == "linux" and machine in ("x86_64", "amd64"):
        return f"actions-runner-linux-x64-{plain}.tar.gz"
    if system == "linux" and machine in ("aarch64", "arm64"):
        return f"actions-runner-linux-arm64-{plain}.tar.gz"
    if system == "darwin" and machine in ("arm64", "aarch64"):
        return f"actions-runner-osx-arm64-{plain}.tar.gz"
    if system == "darwin" and machine == "x86_64":
        return f"actions-runner-osx-x64-{plain}.tar.gz"
    raise Refused(f"no GitHub runner build for {system}/{machine}")


def supports_services(system: str) -> bool:
    """Only Linux keeps a runner alive here today; macOS needs launchd and is not written yet."""
    return system == "linux"
