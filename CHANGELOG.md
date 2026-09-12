# Changelog

## 0.1.0 (2026-09-12)

- `homerunner add`, `list`, `remove`, `doctor`.
- Refuses to register a runner against a public repository, because a pull request from anyone
  would then run code on the machine. `--i-know-this-is-public` overrides it deliberately.
- One runner and one user service per repository, scoped to that repository.
- `Nice=15` and `IOSchedulingClass=idle` by default, so CI yields to what the machine is for.
- No token of its own: credentials come from the `gh` CLI, and the registration token is passed
  straight to `config.sh` without touching disk.
- `--ephemeral` for a runner that takes one job and exits.
