# homerunner

**Run your private repositories' CI on a machine you already own** — one command per repository,
and a flat refusal to do the thing that would hurt you.

[![tests](https://github.com/YauhenBichel/homerunner/actions/workflows/tests.yml/badge.svg)](https://github.com/YauhenBichel/homerunner/actions/workflows/tests.yml)
[![License: Apache-2.0](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)

GitHub Actions minutes are free on public repositories and metered on private ones. When the quota
runs out, every job fails before it runs a step — `steps=0`, which looks like a broken build and
isn't one. Meanwhile there is a perfectly good machine under your desk doing nothing between tasks.

```bash
pip install homerunner
homerunner add YauhenBichel/llm-harness
```

That registers a runner for that repository, installs a user service that keeps it alive, and tells
you what to put in the workflow:

```
  runner 2.337.0 -> /home/yauhen/.local/share/homerunner/yauhenbichel-llm-harness
  labels: self-hosted, yserver
  service homerunner-yauhenbichel-llm-harness: active

Point a workflow at it:

  runs-on: [self-hosted, yserver]
```

## The refusal

```console
$ homerunner add YauhenBichel/moe-fit
homerunner: YauhenBichel/moe-fit is public. A self-hosted runner on a public repository runs code
from anyone's pull request on this machine, with your files and your keys. Use a hosted runner, or
pass --i-know-this-is-public if this machine is disposable.
```

This is the feature. A self-hosted runner on a public repository will execute whatever a stranger
puts in a pull request, on the machine it runs on — your keys, your home directory, your models.
GitHub documents it; people do it anyway, because nothing stops them at the moment it happens.
`homerunner` stops them at exactly that moment.

## What it decides for you

- **One runner per repository, scoped to that repository.** Not one account-wide credential that
  could build anything you own.
- **`Nice=15` and `IOSchedulingClass=idle`.** CI yields to whatever the machine is really for. On
  the box this was written for, that is a 52 GB model; a test run waits its turn.
- **`KillMode=process`**, so a job in flight finishes rather than being killed mid-write.
- **A user service**, so no root is needed, and a warning if lingering is off — without it your
  runner stops when you log out.
- **No token of its own.** Everything that needs credentials goes through the `gh` CLI you have
  already signed in. The registration token it fetches lives for an hour and never reaches disk.
  There is nothing here worth stealing.

## Commands

```bash
homerunner add <owner/repo>     # register, install, start
homerunner list                 # what this machine runs, and what GitHub thinks of it
homerunner remove <owner/repo>  # deregister and take the service away (--purge deletes the files)
homerunner doctor               # can this machine host a runner at all?
```

`doctor` first, always:

```console
$ homerunner doctor
  yes  the gh CLI is installed
  NO   gh is signed in
       gh auth login
  yes  this is Linux (systemd user services): linux
  yes  systemctl is available
  yes  user services survive logout (lingering)
```

Useful flags: `--ephemeral` (the runner takes one job and exits, which is the safest shape),
`--label gpu` (extra labels a workflow can target), `--nice` and `--io-class` if the defaults are
too polite, `--runner-version` to pin.

## What it is not

- **Not an autoscaler.** [Actions Runner Controller](https://github.com/actions/actions-runner-controller)
  does that on Kubernetes, and does it properly. This is for one machine you can touch.
- **Not isolation.** An ephemeral runner gets a clean workspace, not a clean machine. If you need
  the job in a sandbox, run the job in a container, or use a VM-based tool such as
  [SHER](https://github.com/pranau97/sher).
- **Not a way to make a public repository cheap.** See the refusal above.
- **Linux only, today.** The runner itself works on macOS; keeping it alive there needs launchd,
  which is not written yet. `doctor` says so rather than pretending.

## Requirements

Linux with systemd, Python 3.10+, and the [`gh` CLI](https://cli.github.com) signed in with admin
on the repositories you point it at. No other dependencies.

## Contributing

Issues and pull requests welcome — see [CONTRIBUTING.md](CONTRIBUTING.md). The tests replace
`subprocess.run`, so the whole suite runs in well under a second with no network, no `gh` and no
runner:

```bash
uv run pytest -q
```

## Contributors

Thank you to everyone who has helped.

<!-- readme: contributors,bots/- -start -->
<p align="center">
  <a href="https://github.com/YauhenBichel" title="Yauhen Bichel" aria-label="Yauhen Bichel"><img src=".github/faces/YauhenBichel.svg" width="87" height="99" alt="Yauhen Bichel" /></a>
</p>
<!-- readme: contributors,bots/- -end -->

## Licence

Apache-2.0. See [LICENSE](LICENSE).
