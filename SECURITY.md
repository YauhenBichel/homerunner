# Security

## Reporting

Please report a vulnerability through GitHub's private advisory form on this repository
("Security" → "Report a vulnerability"), not in a public issue. I aim to reply within a week.

## The threat this tool exists to prevent

A self-hosted runner on a **public** repository executes code from any pull request, on the machine
it runs on. `homerunner add` refuses public repositories for that reason. The override
(`--i-know-this-is-public`) is for machines you are prepared to lose.

## What homerunner holds

- **No tokens.** Credentials come from the `gh` CLI you signed in. The registration token is
  fetched, passed to `config.sh` as an argument, and never written to disk by this tool.
- **One runner per repository**, registered to that repository only — not to your account or an
  organisation. A compromised job can reach what that repository's workflows can reach, and the
  machine's own user account, but not your other repositories' runners.

## What it does not give you

Isolation. `--ephemeral` gives each job a fresh runner registration and workspace, not a fresh
machine: a job still runs as your user, with your home directory. If you need more than that, run
the work in a container inside the job, or use a VM-per-job tool.
