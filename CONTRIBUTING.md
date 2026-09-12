# Contributing

Issues and pull requests are welcome.

## Running the tests

```bash
uv run pytest -q
```

They replace `subprocess.run`, so nothing reaches the network, no `gh` is needed and no runner is
downloaded. The whole suite is well under a second.

## What would help most

- **macOS support.** The runner works there; keeping it alive needs launchd instead of a systemd
  user service. `plan.supports_services` is where that decision lives, and `doctor` already says
  the platform is unsupported rather than pretending.
- **Reports from other machines.** Different distributions, cgroup settings and `loginctl`
  behaviour are where this will break first.

## The shape of the code

- `plan.py` has the decisions and touches nothing. Anything that can be a pure function goes there,
  which is why the safety rules are easy to test.
- `github.py` talks to `gh` only. It must never learn to read a token from a file or the
  environment: having nothing worth stealing is a feature, not an oversight.
- `machine.py` is the part with side effects.
- Claims in comments carry their evidence. If you state a number, say where it was measured.
