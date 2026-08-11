# Build and publish the guide

**Who this is for:** the operator turning generated IG source into the
browsable, publishable site - and keeping the build fast.

**Before you start:** a generated project ([Generate the IG
source](201-generate.md)), Docker running, and network access to a FHIR
terminology server (or a plan for offline, below).

**You will be able to:**

- compile the FSH as a fast gate, and run the full publisher when it counts
- drive every step through the scaffolded Makefile
- size the build - what the registry costs, what the caches buy back
- read the publisher's exit codes instead of guessing

## Build it

```bash
make setup      # once: build the SUSHI + IG publisher docker image
make sushi      # fast gate: compile FSH to FHIR resources, no site
make build      # the full IG publisher; the site lands in ig/output/
```

The scaffolded Makefile is the whole workflow - every target reads the same
`fhir.toml`:

| Target | Does |
| --- | --- |
| `help` | List the targets. |
| `setup` | Build the SUSHI + IG publisher docker image. |
| `upgrade` | Rebuild it from scratch, pulling the latest of both. |
| `generate` | `d2w fhir generate`. |
| `update` | Move the toolchain pin (`uv lock --upgrade`), sync, `d2w fhir init --refresh`. |
| `validate` | `d2w fhir validate`. |
| `cache-init` | Make the shared package-cache volume writable by the publisher user. |
| `sushi` | Compile FSH to FHIR resources. |
| `build` | Run the full IG publisher. |
| `serve` | Serve the compiled IG as a FHIR endpoint (run `generate` + `sushi` first). |
| `serve-live` | Serve straight from the DHIS2 instance, no compile needed. |
| `serve-ui` | Serve the FHIR endpoint plus the capture UI at `/`. |
| `forward` | Dry-run the capture spool against DHIS2 - nothing written, nothing moved. |
| `forward-import` | Import the capture spool into DHIS2. |
| `clean` | Remove build output (keeps `ig/input-cache`). |
| `clean-all` | Also remove the terminology cache and the package cache volume. |
| `refresh` | Force-refresh everything: `clean-all`, `upgrade`, `generate`, `validate`, `build`. |

`refresh` runs `validate` with a leading dash - `-$(MAKE) validate`. A full
rebuild wants fresh reports out of the instance every time, and validate
exits 1 whenever the instance carries code errors, which is by design and
must not abort the rebuild. Every other step stops the chain on failure.
`refresh` also has no `sushi` step: the publisher runs its own SUSHI over
the same FSH, so a chain calling both compiles everything twice.

`generate` and `validate` call `d2w` through a `D2W` variable, defaulting to
`uv run d2w` - the pinned toolchain. Override it to drive a checkout or a
git ref instead:

```bash
# From a local checkout of dhis2w-utils:
make generate D2W="uv run --project /path/to/dhis2w-utils d2w"

# Straight from a git ref, nothing installed, no uv sync:
make generate D2W="uvx --from 'git+ssh://git@github.com/winterop-com/dhis2w-utils.git@main#subdirectory=packages/dhis2w-cli' --with 'dhis2w-fhir @ git+ssh://git@github.com/winterop-com/dhis2w-utils.git@main#subdirectory=packages/dhis2w-fhir' d2w"
```

!!! warning "Do not iterate on `make build`"
    `d2w fhir generate` followed by `make sushi` compiles the FSH and tells
    you whether it is valid without paying for a published site. Run the
    publisher when you are ready to publish one, not after every edit.

## Turn the three build knobs

The scaffold sets all three, the first two because the defaults break on a
real instance's IG.

**The SUSHI timeout** - `ig/fsh.ini` raises it to 1800 seconds, settable at
scaffold time with `d2w fhir init --sushi-timeout`. The IG publisher re-runs
SUSHI internally with a 300-second default, which the FSH of a real
instance's IG overruns easily; the publisher then dies with exit 143 in its
very first phase:

```text
Sushi timeout exceeded: 1800 seconds
Exception: Process exited with an error: 143 (Exit value: 143)
```

**`TX_SERVER`** picks the terminology server the publisher validates
against; it defaults to `http://tx.fhir.org`. `TX_SERVER=n/a` disables
terminology validation for an offline build, but current publisher versions
throw a `NullPointerException` on required bindings that need a server - the
`Attachment.contentType` binding on the GeoJSON boundary extension is one,
so an org-unit IG will not build offline. Use `n/a` only when your content
has no such bindings.

**`JAVA_HEAP`** is the publisher's JVM heap, `4g` by default - the knob for
exit 137:

```text
Generating Summary Outputs (en)
make: *** [build] Error 137
```

137 is `128 + 9` - SIGKILL from the kernel's OOM killer. The give-away is
that `ig/output` is empty afterwards: the publisher writes the site in one
pass at the very end, so a build killed in the peak-memory phases leaves
nothing behind. A real build error looks nothing like this - a Java stack
trace, a different exit code, partial output on disk. The container carries
no `--memory` limit, so it inherits the docker VM's allocation, and a 4 GB
heap needs roughly 6 GB of room once metaspace, JVM native memory, and the
OS are counted:

```bash
docker info --format '{{.MemTotal}}'    # bytes available to the docker VM
make build JAVA_HEAP=2g                 # when you cannot raise the VM
```

Raising the VM's memory is the better fix; confirm a suspected OOM kill by
dropping `--rm` from the `build` recipe and running
`docker inspect <container> --format '{{.State.OOMKilled}}'`.

## Size the build

All figures below were measured on real instances (the Sierra Leone demo:
171 option sets, 2,664 registry instances, 3,101 resources; the uncapped
Lao national instance: 235 option sets, 25,162 registry instances).

Generation is the cheap half; the toolchain is where the minutes go. On the
demo, `generate` is 16s and `validate` 7s; a national instance generates in
a few minutes.

**The registry is usually the largest thing in the IG by a wide margin** -
every unit emits an Organization and a Location, and a hierarchy fans out at
the bottom:

| Level | Units | Instances |
| --- | --- | --- |
| 1 | 2 | 4 |
| 2 | 33 | 66 |
| 3 | 447 | 894 |
| 4 | 1,867 | 3,734 |
| 5 | 10,232 | 20,464 |
| **total** | **12,581** | **25,162** |

Level 5 alone is 81% of that registry. The registry ships as pre-built JSON
SUSHI never compiles, but the publisher writes and renders a page per
resource - so the registry sets the wall clock of `make build`, and
`[generate.organisation_units]` `max_level` / `root` is the lever on the
*published* size (25,162 instances down to 4,698 with `max_level = 4`), not
on the compile.

**What the compile costs** - `make sushi` runs SUSHI directly, no timeout,
so it measures the compile: 6m57s on the uncapped Lao IG, warm cache. What
that buys is the FSH: the forms and five compiled CodeSystems, dominated by
the two data-dictionary files (2.5MB of FSH). Writing the 235 option sets
as FSH instead of predefined JSON would add 3m18s; fewer selected forms
mean smaller dictionary files. Docker is not where the time goes: the bind
mount costs about 5 seconds on a 23-minute compile, and running SUSHI
natively saves about 22% - the rest is SUSHI's own work.

**What the publisher pays for** is sheer resource count, not terminology
service time (connecting to `TX_SERVER` and opening the cache cost about
fourteen seconds together). The scaffolded `sushi-config.yaml` publishes
JSON only (`excludexml`, `excludettl`), which on the demo halves the output:
13,710 files and 466MB instead of 26,120 and 874MB, same 0 errors and 0
warnings.

## Keep the caches warm

Most of what a repeat build would re-pay is cached, and the scaffold wires
both up:

- **The FHIR package cache** is the named docker volume `fhir-ig-cache`,
  mounted at `~/.fhir` in the container by `make sushi` and `make build`
  (both depend on `make cache-init`, which chowns the volume - a fresh
  volume is root-owned and the publisher's non-root user cannot write to
  it). Without it every run re-downloads the core packages first - about
  three and a half minutes of pure download.
- **The terminology cache** is `ig/input-cache/`, written by the publisher
  and ignored by git. `make clean` deliberately leaves it in place; a warm
  tx cache takes the validation phase from minutes to seconds.

`make clean-all` drops both when you want to reproduce a cold build.

## Publish it

The generated site lands in `ig/output/` - plain static files. Publish them
however your organisation hosts static sites; the canonical URL you
scaffolded with is where consumers will expect to find it. Before handing
it over, read `ig/output/qa.html` - the publisher's own QA summary of
errors, warnings, and broken links.

Next: [Serve the IG](201-serve.md) - the compiled guide, answered live as a
FHIR endpoint.
