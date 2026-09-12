# Copyright 2026 Yauhen Bichel
# SPDX-License-Identifier: Apache-2.0
"""homerunner: run your private repositories' CI on a machine you already own.

  homerunner add <owner/repo>     register a runner for this repository and keep it running
  homerunner list                 what this machine runs, and what GitHub thinks of it
  homerunner remove <owner/repo>  deregister it and take the service away
  homerunner doctor               is this machine able to host a runner at all?

It stores no token: everything that needs credentials goes through the `gh` CLI you already signed
in, and the registration token it fetches lives for an hour and is never written to disk.
"""
from __future__ import annotations

import argparse
import platform
import shutil
import sys
from pathlib import Path

from . import github, machine
from .plan import (
    DEFAULT_IO_CLASS,
    DEFAULT_NICE,
    Refused,
    check_allowed,
    labels,
    parse_repo,
    runner_dir,
    supports_services,
    unit_name,
)

ROOT = Path.home() / ".local" / "share" / "homerunner"
CACHE = Path.home() / ".cache" / "homerunner"


def cmd_add(args: argparse.Namespace) -> int:
    repo = parse_repo(args.repo)
    if not supports_services(platform.system().lower()):
        raise Refused(f"{platform.system()} is not supported yet: this installs a systemd user "
                      f"service, and only Linux has one. The runner itself would work.")

    facts = github.facts(repo)
    check_allowed(repo, facts, force_public=args.i_know_this_is_public)
    if not facts.private:
        print("WARNING: this repository is public. Anyone's pull request can run code here.\n")

    version = args.runner_version or github.latest_runner_version()
    directory = runner_dir(ROOT, repo)
    print(f"  runner {version} -> {directory}")
    machine.download_runner(version, directory, CACHE)

    chosen = labels(args.label, args.host)
    print(f"  labels: self-hosted, {', '.join(chosen)}")
    machine.configure(directory, repo, github.registration_token(repo),
                      args.name or chosen[0], chosen, args.ephemeral)

    unit = machine.install_service(repo, directory, args.nice, args.io_class, args.ephemeral)
    print(f"  service {unit}: {machine.is_active(unit)}")
    if not machine.lingering():
        print(f"  NOTE: user services stop when you log out. Turn that off with:\n"
              f"        sudo loginctl enable-linger {Path.home().name}")
    print(f"\nPoint a workflow at it:\n\n  runs-on: [self-hosted, {chosen[0]}]\n")
    return 0


def cmd_remove(args: argparse.Namespace) -> int:
    repo = parse_repo(args.repo)
    unit = machine.remove_service(repo)
    directory = runner_dir(ROOT, repo)
    try:
        machine.unregister(directory, github.removal_token(repo))
        print(f"  deregistered from {repo.slug}")
    except Refused as exc:
        print(f"  could not deregister from GitHub ({exc}); remove it in the repository settings")
    if args.purge and directory.exists():
        shutil.rmtree(directory, ignore_errors=True)
        print(f"  removed {directory}")
    print(f"  service {unit} gone")
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    if not ROOT.exists() or not any(ROOT.iterdir()):
        print("no runners on this machine yet: homerunner add <owner/repo>")
        return 0
    print(f"{'repository':34} {'service':10} {'github':10} labels")
    for directory in sorted(p for p in ROOT.iterdir() if p.is_dir()):
        owner, _, name = directory.name.partition("-")
        slug = f"{owner}/{name}"
        try:
            repo = parse_repo(slug)
        except Refused:
            continue
        unit = unit_name(repo)
        local = machine.is_active(unit)
        remote, marks = "unknown", ""
        if not args.local:
            try:
                found = github.runners(repo)
                remote = found[0]["status"] if found else "not registered"
                marks = ", ".join(found[0]["labels"]) if found else ""
            except Refused as exc:
                remote = "gh failed"
                marks = str(exc)[:40]
        print(f"{slug:34} {local:10} {remote:10} {marks}")
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    system = platform.system().lower()
    ok = True

    def line(good: bool, text: str, fix: str = "") -> None:
        nonlocal ok
        ok = ok and good
        print(f"  {'yes' if good else 'NO ':4} {text}")
        if not good and fix:
            print(f"       {fix}")

    line(shutil.which("gh") is not None, "the gh CLI is installed", "https://cli.github.com")
    who = github.signed_in_as() if shutil.which("gh") else None
    line(who is not None, f"gh is signed in{f' as {who}' if who else ''}", "gh auth login")
    line(supports_services(system), f"this is Linux (systemd user services): {system}",
         "the runner works elsewhere; homerunner cannot keep it alive there yet")
    if supports_services(system):
        line(shutil.which("systemctl") is not None, "systemctl is available")
        line(machine.lingering(), "user services survive logout (lingering)",
             f"sudo loginctl enable-linger {Path.home().name}")
    try:
        print(f"  ---  latest runner release: {github.latest_runner_version()}")
    except Refused as exc:
        line(False, f"could not ask GitHub for the runner version: {exc}")
    return 0 if ok else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="homerunner", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    add = sub.add_parser("add", help="register a runner for a repository on this machine")
    add.add_argument("repo", help="owner/repository, or its URL")
    add.add_argument("--name", default=None, help="runner name (default: this machine's name)")
    add.add_argument("--label", action="append", default=[], help="an extra label; may be repeated")
    add.add_argument("--host", default=None, help="override the host label")
    add.add_argument("--nice", type=int, default=DEFAULT_NICE,
                     help=f"scheduling niceness, higher yields more (default {DEFAULT_NICE})")
    add.add_argument("--io-class", default=DEFAULT_IO_CLASS, choices=("idle", "best-effort"),
                     help=f"IO priority (default {DEFAULT_IO_CLASS})")
    add.add_argument("--ephemeral", action="store_true",
                     help="the runner takes one job and exits (re-register it to take another)")
    add.add_argument("--runner-version", default=None, help="pin the runner release")
    add.add_argument("--i-know-this-is-public", action="store_true",
                     help="register against a public repository anyway; anyone's pull request "
                          "would then run code on this machine")
    add.set_defaults(func=cmd_add)

    rm = sub.add_parser("remove", help="deregister a runner and remove its service")
    rm.add_argument("repo")
    rm.add_argument("--purge", action="store_true", help="also delete the runner directory")
    rm.set_defaults(func=cmd_remove)

    ls = sub.add_parser("list", help="runners on this machine")
    ls.add_argument("--local", action="store_true", help="do not ask GitHub")
    ls.set_defaults(func=cmd_list)

    doc = sub.add_parser("doctor", help="can this machine host a runner?")
    doc.set_defaults(func=cmd_doctor)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(args.func(args))
    except Refused as exc:
        print(f"homerunner: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
