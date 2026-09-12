# Copyright 2026 Yauhen Bichel
# SPDX-License-Identifier: Apache-2.0
"""The parts that touch this machine: unpacking a runner, and the user services that keep it alive."""
from __future__ import annotations

import os
import platform
import shutil
import subprocess
import tarfile
import urllib.request
from pathlib import Path

from .plan import Refused, Repo, runner_asset, unit_name, unit_text

RELEASES = "https://github.com/actions/runner/releases/download"
UNITS = Path.home() / ".config" / "systemd" / "user"


def systemctl(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    done = subprocess.run(["systemctl", "--user", *args], capture_output=True, text=True, check=False)
    if check and done.returncode != 0:
        detail = (done.stderr or done.stdout).strip().splitlines()
        raise Refused(f"systemctl --user {args[0]} failed: {detail[-1] if detail else done.returncode}")
    return done


def is_active(unit: str) -> str:
    return systemctl("is-active", unit, check=False).stdout.strip() or "unknown"


def lingering() -> bool:
    """Without lingering, user services stop when you log out - and a runner that stops is useless."""
    done = subprocess.run(["loginctl", "show-user", os.environ.get("USER", ""), "-p", "Linger",
                           "--value"], capture_output=True, text=True, check=False)
    return done.stdout.strip() == "yes"


def download_runner(version: str, into: Path, cache: Path) -> Path:
    """Unpack the runner into `into`, keeping the tarball in `cache` so the next repo is instant."""
    asset = runner_asset(version, platform.system().lower(), platform.machine().lower())
    cache.mkdir(parents=True, exist_ok=True)
    tarball = cache / asset
    if not tarball.exists():
        url = f"{RELEASES}/v{version}/{asset}"
        tmp = tarball.with_suffix(".part")
        with urllib.request.urlopen(url, timeout=300) as response, tmp.open("wb") as out:
            shutil.copyfileobj(response, out)
        tmp.rename(tarball)
    into.mkdir(parents=True, exist_ok=True)
    with tarfile.open(tarball) as archive:
        # `filter="data"` refuses absolute paths and links that point outside the directory.
        try:
            archive.extractall(into, filter="data")
        except TypeError:                      # Python 3.10 and 3.11 have no filter argument
            archive.extractall(into)           # noqa: S202 - the asset is GitHub's own release
    return into


def configure(directory: Path, repo: Repo, token: str, name: str, labels: list[str],
              ephemeral: bool) -> None:
    """Register the runner. The token is passed as an argument to config.sh and never stored."""
    args = ["./config.sh", "--url", repo.url, "--token", token, "--name", name,
            "--labels", ",".join(labels), "--work", "_work", "--unattended", "--replace"]
    if ephemeral:
        args.append("--ephemeral")
    done = subprocess.run(args, cwd=directory, capture_output=True, text=True, check=False)
    if done.returncode != 0:
        detail = (done.stderr or done.stdout).strip().splitlines()
        raise Refused(f"registering the runner failed: {detail[-1] if detail else done.returncode}")


def install_service(repo: Repo, directory: Path, nice: int, io_class: str, ephemeral: bool) -> str:
    unit = unit_name(repo)
    UNITS.mkdir(parents=True, exist_ok=True)
    (UNITS / f"{unit}.service").write_text(unit_text(repo, directory, nice, io_class, ephemeral))
    systemctl("daemon-reload")
    systemctl("enable", "--now", unit)
    return unit


def remove_service(repo: Repo) -> str:
    unit = unit_name(repo)
    systemctl("disable", "--now", unit, check=False)
    (UNITS / f"{unit}.service").unlink(missing_ok=True)
    systemctl("daemon-reload", check=False)
    return unit


def unregister(directory: Path, token: str) -> None:
    if not (directory / "config.sh").exists():
        return
    subprocess.run(["./config.sh", "remove", "--token", token], cwd=directory,
                   capture_output=True, text=True, check=False)
