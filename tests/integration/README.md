# Integration tests

End-to-end proxy client integration tests with real KeePassXC instance.

Integration test components:

- KeePassXC is launched headless inside Docker container.
- noVNC UI is spawned on http://localhost:6080 for interaction
- Docker-managed volume houses the KeePassXC unix-domain socket accessed by client

---

## Prerequisites

- **Docker** — Docker Desktop on macOS / Windows, Docker Engine on Linux.
  `docker compose` (v2) is required.
- A modern browser (for the noVNC UI on http://localhost:6080).
- Port `6080` available on the host.

---

## Quick start

```bash
docker compose -f tests/integration/docker/docker-compose.yml up --build
```

When a test pauses on a human action, **open http://localhost:6080 in a
browser** and perform the action shown in the test output (e.g. *"click Allow
in the association dialog"*). Press <kbd>Enter</kbd> in the terminal running
`docker compose` once the action is done, and the test resumes.

To stop and clean up:

```bash
docker compose -f tests/integration/docker/docker-compose.yml down -v
```

(`-v` also removes the `kpxc-socket` named volume, so the next run starts
from scratch.)

---

## Pinning a specific KeePassXC version

The Dockerfile takes a `KPXC_VERSION` build argument. Without it, the latest
available package from the official KeePassXC repository is installed.

```bash
KPXC_VERSION=2.7.9 docker compose \
    -f tests/integration/docker/docker-compose.yml \
    up --build
```

---

## The test database

The suite uses `tests/integration/fixtures/test.kdbx`. **Master password:
`test`**.

| Path | URL | Login | Password | Notes |
| --- | --- | --- | --- | --- |
| `example.com` | `https://example.com` | `alice` | `hunter2` | Single-match URL lookup. |
| `duplicate-url-1` | `https://dup.example` | `u1` | `p1` | Multi-match URL lookup. |
| `duplicate-url-2` | `https://dup.example` | `u2` | `p2` | Multi-match URL lookup. |
| `totp-entry` | `https://totp.example` | `totpuser` | `totppw` | Has TOTP seed `JBSWY3DPEHPK3PXP`. |
| `attr-entry` | `https://attr.example` | `attruser` | `attrpw` | Custom string `KPH: api-key` = `sk-test-1234`. |
| `Work/nested-entry` | `https://work.example` | `bob` | `bobpw` | Nested under group `Work`. |

The fixture is committed so first run requires zero setup. It contains only
fake secrets — safe to keep in git.

### Recreating the fixture

If you change what tests expect, rebuild the kdbx from source:

```bash
uv run python tests/integration/fixtures/build_kdbx.py
```

The builder uses `pykeepass` (declared in the project's `dev` dependency
group, installed automatically by `uv sync`).

You can also create the database by hand in KeePassXC's GUI; match the table
above exactly. Be sure to set the master password to `test`.

---

## Running a single test

Once the stack is up you can re-run individual tests against the same
keepassxc service without restarting it:

```bash
docker compose -f tests/integration/docker/docker-compose.yml \
    run --rm client \
    uv run pytest tests/integration/test_get_logins.py -v
```

Or, if you'd rather not use the client container (e.g. you have `uv` on the
host and want a faster edit/test loop):

```bash
# 1. Start only the keepassxc service.
docker compose -f tests/integration/docker/docker-compose.yml \
    up -d --build keepassxc

# 2. Expose the named volume to your host (Linux only — macOS/Windows must
#    use the client container, since the socket is in Docker's vfs).
SOCKET=$(docker volume inspect kpxc-test_kpxc-socket -f '{{ .Mountpoint }}')
XDG_RUNTIME_DIR="$SOCKET" uv run pytest tests/integration -m integration -v
```

---

## Human interactions during the run

| Test | Action expected at http://localhost:6080 |
| --- | --- |
| `test_associate.py::test_associate_and_persist` | In the association dialog, type `integration-test` and click **Allow**. |
| `test_associate.py::test_test_associate_against_saved` | Click **Allow** in the association dialog. |
| `test_get_logins.py::*` | Click **Allow** once at the start of the suite. |
| `test_get_by_path.py::*` | Click **Allow**, then enable **"Allow access to entries"** in *Database → Database Settings → Browser Integration → integration-test*. |
| `test_totp.py::*` | Click **Allow** once. |
| `test_unlock.py::*` | Click **Allow**, then **Database → Lock Databases**, then enter master password `test` when the unlock dialog appears. |
| `test_lock_states.py::*` | Click **Allow**, then **Database → Lock Databases** when prompted, then unlock when prompted. |

Each prompt is printed to the test output with a clear banner.

---

## Troubleshooting

**Port 6080 already in use.** Stop whatever's holding it, or change the
host-side port in `docker-compose.yml` (e.g. `6081:6080`). Open
http://localhost:6081 instead.

**Socket permission denied.** Both containers must run as uid 1000. If
you've customized the image, double-check `USER kpxc` in the keepassxc
Dockerfile and the `useradd -u 1000` in the client Dockerfile.

**Tests hang at `press ENTER once done...`.** That's the `human_step`
prompt — open the noVNC URL in a browser, perform the action, then press
<kbd>Enter</kbd> in the terminal. If you're running in CI or a headless
context, set `KPXC_TEST_AUTOCONFIRM=1` and the prompts become timed pauses
(default 10s — override with `KPXC_TEST_HUMAN_WAIT=N`). This mode assumes
something else is performing the click (e.g. an `xdotool` script inside the
keepassxc container — not implemented in this pass).

**Image rebuild after Dockerfile edits.** `docker compose ... up --build`
rebuilds. To force a clean rebuild: `docker compose ... build --no-cache`.

**Where are the logs?** Supervisord writes per-program logs to `/tmp/*.log`
inside the keepassxc container. `docker compose logs keepassxc` shows
stdout/stderr from supervisord itself.
