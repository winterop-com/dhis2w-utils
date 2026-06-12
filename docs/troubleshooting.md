# Troubleshooting

What we found chasing macOS hard-freezes during multi-Claude-Code workloads. **The repo's own code is clean** — every loop and async fan-out is bounded. The freezes came from elsewhere; the rest of this doc is what to check.

## What actually caused the macOS freezes

Three signals taken together:

1. **No kernel panic file** in `/Library/Logs/DiagnosticReports/`. The system hung; the kernel didn't formally panic. That rules out a driver crash (Docker's vmnet kext, etc.) — those leave a `.panic` file.
2. **9 Python 3.13 SIGSEGV crashes** in user crash logs over 4 days, all `EXC_BAD_ACCESS / KERN_INVALID_ADDRESS`. That's a native C extension memory violation (pydantic-core / cryptography / lxml / Pillow / httpcore-rs are the usual suspects). Crashes alone don't freeze the OS, but a constant trickle of native-extension corruption alongside heavy memory pressure means processes die in unhelpful ways.
3. **One docker container with no memory limit ate everything during an INLA-style workload.** A live `docker stats` snapshot showed `chap-core-worker-1` running unbounded (Docker reports the host RAM ceiling, 15.6 GiB, when no `mem_limit` is set in compose). Idle, the worker is ~1.5 GiB. During an INLA evaluation it spikes to 4-8 GiB. With DHIS2 (~3 GiB) + Postgres (~4 GiB) + idle chap workload + the host running 4-5 Claude sessions + Chrome, the host went into severe memory pressure. macOS could not page out fast enough; user input stopped being scheduled; only a hard restart recovered.

So: **memory pressure from one unbounded container during a workload spike**, not a fork bomb, not a loop, not a kext panic.

## What recurring native segfaults mean

`python3.13` SIGSEGVs in `~/Library/Logs/DiagnosticReports/python3.13-*.ips` are coming from a C extension. Look at the most recent one:

```bash
latest=$(ls -t ~/Library/Logs/DiagnosticReports/python3.13-*.ips 2>/dev/null | head -1)
head -60 "$latest"
```

The interesting fields:

- `parentProc` — what spawned the process (`ghostty`, `pytest`, `pycharm`, …). Tells you which workflow is the trigger.
- `responsibleProc` — the highest-level process responsible. Often a terminal.
- `exception.subtype` — `KERN_INVALID_ADDRESS at 0x...` says native pointer corruption.
- The thread backtrace below the header — first non-Python frame names the offending C library.

Common culprits:

| Library | Smell | Mitigation |
| --- | --- | --- |
| `pydantic-core` (Rust) | Crashes during model validation under heavy concurrency | Pin to latest; older releases had real bugs |
| `cryptography` (Rust+OpenSSL) | Crashes during TLS handshake | `uv lock --upgrade-package cryptography && uv sync` |
| `lxml` (libxml2) | Crashes during XML parsing | Rare for our workload, but possible if an example hits a tracker XML import |
| `Pillow` (libpng/libjpeg) | Crashes during image decode | `dhis2w-browser` screenshot capture is the only path that does this |
| `httpcore-rs` / `h11` | Crashes during connection close | Switching to httpx 0.28+ helps |

Once-or-twice in a week is unusual but tolerable. Daily, with a stable repro, file a bug at the offending library. Until you have a fix, run Python with `faulthandler` on so you get a Python-level traceback at SIGSEGV time:

```bash
PYTHONFAULTHANDLER=1 uv run pytest ...
# or in code: `import faulthandler; faulthandler.enable()` at startup
```

## Resource budgets that survive contention

For a typical Apple Silicon dev machine (32-64 GB RAM) running 4-5 Claude Code sessions + browser + IDE:

| Budget | Policy |
| --- | --- |
| **Docker Desktop memory cap** | 6-8 GB unless you specifically need the full DHIS2 e2e seed. The default 16 GB is too generous given everything else you run. Set in Settings → Resources → Memory. |
| **Per-container `mem_limit`** | **Always set one in `compose.yml` for any container that runs computation.** Without it, Docker reports the VM ceiling as the limit, which means the container can eat all of Docker's memory. The DHIS2 container in this repo's `infra/compose.yml` is capped at 5g already; if you wire up new compose stacks (chap-core, chap-scheduler, anything similar), audit each `services:` block for a `deploy.resources.limits.memory` or `mem_limit` key. |
| **Multiple compose stacks running simultaneously** | Avoid. Docker's VM doesn't shrink when containers stop; running two stacks in a day means the VM stays at the high-water mark even after `docker compose down`. |
| **`uv tool install` over `uvx`** | Each `uvx <pkg>` spawns a fresh resident interpreter per shell. 4 sessions × ~220 MB = ~900 MB just for one tool. `uv tool install` keeps a single resident copy across sessions. |

### The "Docker doesn't release RAM" gotcha

`docker compose down` releases the container, NOT the RAM the Linux VM holds. After a day of `make dhis2-run` cycles plus other stacks, the VM sits at 20+ GB resident even with no containers running. Force release:

```bash
osascript -e 'quit app "Docker"' && open -a Docker
```

## Diagnostic commands when the system is misbehaving

```bash
# 1. Live container memory — the single most useful command. Watch for any `MEM USAGE` near the host ceiling.
docker stats --no-stream --format "table {{.Name}}\t{{.MemUsage}}\t{{.MemPerc}}\t{{.CPUPerc}}"

# 2. Macos memory pressure right now
memory_pressure | tail -10

# 3. Top RAM users
ps aux | sort -k6 -rn | head -10 | awk '{printf "%6.1f MB  %s\n", $6/1024, substr($0, index($0,$11), 80)}'

# 4. Kernel panic log (will be empty if you haven't had a real panic)
ls -lah /Library/Logs/DiagnosticReports/ | grep -i panic

# 5. Recent Python user-process crashes
ls -t ~/Library/Logs/DiagnosticReports/python3.13-*.ips 2>/dev/null | head -5

# 6. Disk free on the volume holding the repo
df -h /Users/$USER
```

## fseventsd / Spotlight protection

`fseventsd` watches every directory by default. Codegen writing 1000 files in a burst, plus Spotlight indexing each one, plus iCloud sync, can saturate the kernel's event pipeline. Exclude noisy paths — drop a hidden marker file fseventsd respects:

```bash
touch /Users/$USER/dev/dhis2w-utils/.venv/.metadata_never_index 2>/dev/null
touch /Users/$USER/dev/dhis2w-utils/site/.metadata_never_index 2>/dev/null
touch /Users/$USER/dev/dhis2w-utils/dist/.metadata_never_index 2>/dev/null
mkdir -p /Users/$USER/dev/dhis2w-utils/.mypy_cache && touch /Users/$USER/dev/dhis2w-utils/.mypy_cache/.metadata_never_index
mkdir -p /Users/$USER/dev/dhis2w-utils/.pytest_cache && touch /Users/$USER/dev/dhis2w-utils/.pytest_cache/.metadata_never_index
```

Or System Settings → Spotlight → Spotlight Privacy → drag in `~/dev/dhis2w-utils/.venv`, `~/dev/dhis2w-utils/site`, `~/dev/dhis2w-utils/dist`, `~/dev/dhis2w-utils/.mypy_cache`, `~/dev/dhis2w-utils/.pytest_cache`.

**Verify the repo isn't on iCloud Drive / Dropbox / OneDrive.** A synced location amplifies every codegen / `uv sync` burst.

## Recovery without a hard restart

```bash
# 1. Stop every docker compose stack on this machine
docker stop $(docker ps -q) 2>/dev/null

# 2. Force Docker Desktop to release its VM RAM (this is the biggest single recovery win)
osascript -e 'quit app "Docker"'

# 3. Clean up any leftover MCP / uvx / playwright processes
pkill -f "dhis2w-mcp" 2>/dev/null
pkill -f "uvx" 2>/dev/null
pkill -f "playwright-mcp" 2>/dev/null

# 4. If memory pressure is still high — close unused Claude Code sessions (each ~700-850 MB) + Chrome tabs
```

## Patterns that bite under multiple Claude Code sessions

These aren't this-repo-specific, but this repo gives you many ways to trigger them:

| Pattern | Why it spirals | What helps |
| --- | --- | --- |
| **Containers with no `mem_limit`** | One bad evaluation eats all RAM. Today's freeze. | Set `deploy.resources.limits.memory` on every service that runs computation. |
| **Docker VM doesn't shrink** | After a day of compose cycles the VM holds 20+ GB even with no containers. | Quit + relaunch Docker Desktop occasionally. Trim its RAM budget. |
| **`mkdocs serve` reload storm** | One session runs `make docs-serve`, another edits `docs/`. mkdocs rebuilds, triggers `make docs-cli` writing to `docs/cli-reference.md`, which mkdocs sees, rebuilds again. Self-feeding. | Don't run `mkdocs serve` while another agent edits the same paths. Use `mkdocs build` (one-shot). |
| **Concurrent `make test` from two sessions** | Both write to `.coverage`, both compete for the `uv` lock at `~/.cache/uv/.lock`. Stale lock → next command hangs. | Run heavy commands from one session at a time. |
| **`uvx <pkg>` cold-start per session** | Each Claude shell spawns a fresh ~220 MB interpreter. 4 sessions × multiple tools = quickly into the GBs. | Prefer `uv tool install` for things you use often. |
| **Background tasks left from prior sessions** | `run_in_background: true` tool calls that an agent never explicitly stops. A cancelled session can leak a 7-minute test run. | Always TaskStop background work when you context-switch. `ps aux \| grep <thing>` after closing a session. |
| **`make dhis2-run` Ctrl-C without `make dhis2-down`** | Ctrl-C tears down the foreground process but containers stay up. Repeated cycles accumulate orphans + volumes. | `make dhis2-down` before closing the shell. |
| **Codegen runs while mkdocs is watching** | Codegen produces ~1000 file events in a few seconds. mkdocs processes each → rebuild → kicks off doc generation → more files. | Stop `mkdocs serve` before running codegen. |

## Loop / fan-out audit for this repo

Every `while True` / `while not` and every `asyncio.gather` in `dhis2w-*` source is bounded. **No infinite loops, no unbounded fan-out.** Verified at v0.6.0:

### `while` loops (7 total)

| Location | Loop | Bound |
| --- | --- | --- |
| `dhis2w-browser/src/.../oauth2.py` (`_read_auth_url`) | Reads stderr lines from `d2w profile login` | EOF guard (`if not line_bytes: raise RuntimeError`); caller wraps in `asyncio.wait_for(timeout=60s)` |
| `dhis2w-client/src/.../tasks.py` (`iter_notifications`) | Task-completion poll | `timeout` arg, default 600s, raises `TaskTimeoutError` |
| `dhis2w-client/src/.../category_combos.py` (`wait_for_coc_generation`) | Poll for COC count | `deadline = loop.time() + timeout_seconds` (default 60s), raises `TimeoutError` |
| `dhis2w-client/src/.../data_values.py` (`_async_file_chunks`) | File chunk reader | EOF guard (`if not chunk: return`) |
| `dhis2w-core/src/.../maintenance/service.py` (`wait_for_task`) | Task-status poll | `deadline = loop.time() + timeout` (default 600s), raises `TimeoutError` |
| `dhis2w-core/src/.../metadata/service.py` (`stream_list`) | Pagination | Breaks when `models == []` or `len(models) < page_size` (server-driven) |
| `dhis2w-core/src/.../oauth2_redirect.py` (server-started wait) | Wait for uvicorn `server.started` | Caller wraps in `asyncio.wait_for(timeout=300s)` |

### `asyncio.gather` / parallel fan-out (10 sites)

| Location | What it fans out | Bound |
| --- | --- | --- |
| `dhis2w-client/.../metadata.py:309` (`search`) | One request per search field | Bounded by the number of search fields (~5) |
| `dhis2w-client/.../metadata.py:385` (`usage`) | One request per `_USAGE_PATTERNS` template | Bounded by the static pattern table |
| `dhis2w-client/.../metadata.py:514` (`patch_bulk`) | One PATCH per (resource, uid, ops) tuple | **`asyncio.Semaphore(concurrency)`** caps concurrent in-flight requests |
| `dhis2w-client/.../metadata.py:593` (`apply_sharing_bulk`) | One POST per (resource, uid) tuple | **`asyncio.Semaphore(concurrency)`** caps concurrent in-flight requests |
| `dhis2w-core/.../doctor/service.py:46,50,84` | Fixed list of metadata + bug probes | Bounded by the static probe lists |
| `dhis2w-core/.../doctor/probes_metadata.py:606` | 3 read calls (programs, stages, DEs) | Bounded by the literal tuple |
| `dhis2w-core/.../files/service.py:94` (`get_many`) | One request per uid | **No semaphore.** Mitigation: caller controls list size; would need to be 10k+ uids before it became a real problem |
| `dhis2w-core/.../metadata/service.py:643` | 2 metadata-export calls | Bounded by the literal pair |
| `dhis2w-core/.../oauth2_redirect.py:113` | Single `create_task(server.serve())` | Single task, awaited |

### Subprocess spawn (5 sites)

All single-spawn-and-wait, no loop:

- `dhis2w-browser/.../oauth2.py:65` — `asyncio.create_subprocess_exec("d2w profile login")`, awaited with `wait_for(timeout=60s)`.
- `dhis2w-codegen/.../emit.py:503,508` — `subprocess.run(["ruff", ...])` after each codegen pass. One-shot.
- `dhis2w-codegen/.../_shared.py:35,40` — same pattern, one-shot.

No `subprocess.Popen` in any loop. No `asyncio.create_task` in any loop. No `multiprocessing` or `concurrent.futures` anywhere in the source.

## Heavy-churn patterns this repo can produce

Worth knowing what each command's footprint is so you can avoid running them at the same time as something else memory-heavy:

| Action | Footprint | Mitigation |
| --- | --- | --- |
| `make dhis2-codegen-play` | ~1000 generated `.py` files | Don't run during `mkdocs serve`; ensure `.venv` etc. are excluded from Spotlight |
| `make dhis2-codegen-all` | ~4000 generated files (4 versions) | Run when nothing else is touching the repo |
| `uv sync` after a pyproject change | Rewrites `~/.venv` (thousands of file ops) | Unavoidable, but doesn't compound if Spotlight-excluded |
| `make refresh-and-verify` | Heavy block I/O against the Docker VM disk image | The single most likely trigger of Docker driver hangs. Don't run while other compose stacks share the same Docker VM. |
| `verify_examples.py` | ~165 subprocesses in series, each ~1-30s | Bounded by per-script `--timeout` (default 300s); SKIP_BY_DEFAULT excludes Playwright-driven ones |
| MCP server (`dhis2w-mcp`) | Long-lived stdio process per host connection, ~220 MB | Constant cost, not a loop. Prefer `uv tool install dhis2w-mcp` over `uvx` to share one resident copy across sessions |

## When in doubt — the smallest reset that helps

```bash
# Exit unused Claude Code sessions (each is ~700-850 MB of RAM)
# Quit Chrome tabs you're not actively using
osascript -e 'quit app "Docker"' && open -a Docker
# Activity Monitor → Memory tab. "Memory Pressure" graph should be green.
```

If memory pressure goes yellow / red and stays there, restart Docker rather than the whole machine — almost always Docker's VM not releasing RAM. If `kernel.panic` files exist in `/Library/Logs/DiagnosticReports/`, that's the moment to swap Docker to QEMU mode in Settings.
