# Build and publish the guide

Generation wrote source files. This step turns them into the thing you hand
over: a static website that documents every data set, program, option set,
and organisation unit the last step read out of your instance, one browsable
page each, with every code and identifier resolvable. It runs in Docker, and
it is the only step in this series with a real machine cost - everything
before it is quick by comparison - so most of this page is about paying that
cost once rather than every time you change something.

**Who this is for:** the operator turning generated source into the
browsable, publishable site - and keeping the build fast.

**Before you start:** a generated project ([Generate the IG
source](201-generate.md)), Docker running, and network access to a FHIR
terminology server (or a plan for offline, below).

**You will be able to:**

- compile the FSH as a fast gate, and run the full publisher when it counts
- refuse a build in seconds that would otherwise have failed in hours
- size the build - what the registry costs, what the caches buy back
- read the publisher's exit codes instead of guessing

## Build it

Both tools live in the scaffolded Docker image, so neither SUSHI, the IG
publisher, nor Java is installed on your machine. Build it once, and make the
shared package-cache volume writable by the publisher's non-root user while you
are there - a freshly created volume is root-owned:

```bash
docker build -t fhir-ig .

docker run --rm -u root -v fhir-ig-cache:/home/publisher/.fhir --entrypoint sh fhir-ig \
    -c "mkdir -p /home/publisher/.fhir/packages && chown -R 1001:1001 /home/publisher/.fhir"
```

Then there are two ways to run the toolchain over `ig/` - SUSHI alone as a fast
gate, or the full publisher:

```bash
# fast gate: compile FSH to FHIR resources, no site
docker run --rm -v $(pwd)/ig:/home/publisher/ig -v fhir-ig-cache:/home/publisher/.fhir \
    fhir-ig sushi .

# the full publisher; the site lands in ig/output/
docker run --rm -v $(pwd)/ig:/home/publisher/ig -v fhir-ig-cache:/home/publisher/.fhir \
    fhir-ig \
    java -Xmx4g -jar /home/publisher/.ig-publisher/publisher.jar ig.ini -ig . -tx http://tx.fhir.org
```

SUSHI alone is the one you run in a loop. It compiles and says whether the
source is valid, in a fraction of what a published site costs:

```console
$ docker run --rm -v $(pwd)/ig:/home/publisher/ig -v fhir-ig-cache:/home/publisher/.fhir fhir-ig sushi .
info  Loaded virtual package sushi-local#LOCAL with 2728 resources
info  Converting FSH to FHIR resources...
info  Converted 27 FHIR StructureDefinitions.
info  Converted 7 FHIR CodeSystems.
info  Converted 7 FHIR ValueSets.
info  Converted 60 FHIR instances.
info  Exporting FHIR resources as JSON...
info  Exported 101 FHIR resources as JSON.
info  Assembling Implementation Guide sources...
info  Assembled Implementation Guide sources; ready for IG Publisher.

========================= SUSHI RESULTS ===========================
| Swish! Nothing but fishnet.            0 Errors      0 Warnings |
===================================================================
```

The 2,728 loaded resources against 101 exported ones is the shape of the
whole project: the registry and the terminology ship as pre-built JSON that
SUSHI loads and passes through, and only the forms and the definitional
layer are compiled from source.

The scaffold's Makefile wraps every command on this page - `setup`, `sushi`,
and `build` are the lines above, with the chown folded in as a prerequisite
and the JVM heap lifted into a `JAVA_HEAP` variable, and `generate` /
`validate` are `uv run d2w fhir generate` / `... validate`. `build` runs one
thing the lines above do not: the artifact scan below, which refuses a doomed
publisher run before it starts. [Set up an IG
project](201-set-up-a-project.md) lists the targets. Only `refresh` does
something no single command above does: it chains clean-all, upgrade,
generate, validate, and build, tolerating validate's exit 1 so a full rebuild
still produces fresh reports, and it deliberately skips SUSHI because the
publisher runs its own over the same FSH.

`d2w fhir generate` and `d2w fhir validate` normally run as `uv run d2w` -
the toolchain `uv.lock` pinned. To drive a checkout or a git ref instead,
spell the source into the command:

```bash
# From a local checkout of dhis2w-utils:
uv run --project /path/to/dhis2w-utils d2w fhir generate

# Straight from a git ref, nothing installed, no uv sync:
uvx --from 'git+ssh://git@github.com/winterop-com/dhis2w-utils.git@main#subdirectory=packages/dhis2w-cli' \
    --with 'dhis2w-fhir @ git+ssh://git@github.com/winterop-com/dhis2w-utils.git@main#subdirectory=packages/dhis2w-fhir' \
    d2w fhir generate
```

!!! warning "Do not iterate on the publisher"
    `d2w fhir generate` followed by the SUSHI-only run compiles the FSH and
    tells you whether it is valid without paying for a published site. Run the
    publisher when you are ready to publish one, not after every edit.

## The build refuses before it begins

`make build` does not go straight to the publisher. Its first line is
`d2w fhir check-artifacts`, a scan of the files on disk for the one thing the
publisher cannot survive: a raw `<` in a DHIS2 name or code. That character
survives every earlier pass, the publisher's own Checking Output HTML step
included, and kills the final AI-markdown pass - hours in, once every resource
has already been rendered, with a message naming a page rather than the object.
[Troubleshooting](201-troubleshooting.md#sushi-and-ig-publisher-failures)
carries that stack trace.

Generation already refuses such a selection. The scan exists because a build
does not read a selection - it publishes whatever `ig/fsh-generated/` and
`ig/input/` hold. Output written before the gate existed, output from an older
toolchain pin, and hand-authored FSH all reach the publisher without ever
passing it.

The recipe asks the CLI's own help before running the scan. A project whose
lock pins a dhis2w-fhir without the command (before 1.8) gets a warning that
names the upgrade (`uv lock --upgrade && uv sync`) and a build that proceeds
unscanned - a missing preflight must never stop a publishable guide.

It reads the same files the publisher reads, through the very predicates the
generate-time refusal uses, and it opens no connection and reads no profile -
so it answers in seconds, offline, on any project:

```console
$ d2w fhir check-artifacts
                        fhir check-artifacts
┌───────────┬────────────────────────────────────────────────┐
│project    │ /home/you/anc-guide                            │
│json files │ 240                                            │
│fsh files  │ 42                                             │
│findings   │ 0                                              │
└───────────┴────────────────────────────────────────────────┘
ok: 282 publishable file(s) scanned; nothing the IG publisher aborts on
```

A stale artifact turns that into a refusal that names the file, the resource,
the element, and the value - three findings here, from one CodeSystem an old
generate wrote:

```console
$ d2w fhir check-artifacts
                        fhir check-artifacts
┌───────────┬────────────────────────────────────────────────┐
│project    │ /home/you/anc-guide                            │
│json files │ 240                                            │
│fsh files  │ 42                                             │
│findings   │ 3                                              │
└───────────┴────────────────────────────────────────────────┘
                    build-aborting artifacts (3)
┏━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━┓
┃File               ┃ Resource  ┃ Field               ┃ Value             ┃
┡━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━┩
│ig/fsh-generated/r │ d2-os-Age │ concept[0].display  │ <5 y              │
│esources/CodeSyste │           │ identifier[0].value │ AGE<5             │
│m-d2-os-Age.json   │           │ title               │ Age (<5 - 49) &   │
│                   │           │                     │ over              │
└───────────────────┴───────────┴─────────────────────┴───────────────────┘
note: what it costs: a name carrying '<' stays byte-true on the resource, and
the IG publisher writes it into pages it strict-parses after writing, so `make
build` aborts in its last pass, once every resource has already been rendered.
error: 3 build-aborting artifact(s) found; exiting 1 before the publisher runs
(--no-fail to suppress)

$ echo $?
1
```

Each finding also carries the one line that answers it, in a `What to do`
column left out above for width. Which line depends on what wrote the file: an
artifact this toolchain generated asks for a rename in DHIS2 or a narrower
`fhir.toml` selection followed by another `d2w fhir generate`, while a
hand-authored FSH source asks for an edit, because no regeneration rewrites
one. `--json` puts the whole typed report on stdout.

The scan covers three trees, and each position it reads is one the emitted
resource carries byte-true into a page:

| Read | Positions | Where the publisher would have died |
| --- | --- | --- |
| `ig/fsh-generated/**/*.json` | `name`, `title`, `display`, `text`, `identifier[].value` | the compiled resources it renders a page each from |
| `ig/input/resources/**/*.json` | the same five | the registry, terminology, and ConceptMap documents SUSHI passes through untouched |
| `ig/input/fsh/**/*.fsh` | `Title:`, assignments to those elements, `* #code "display"` rules | the FSH sources, generated and hand-authored alike |

`ig/input/pagecontent/**/*.md` is deliberately left out: markdown carries HTML
by design, so a `<` there is the page's own markup.

An existing project takes the gate up with one command - `d2w fhir init
--refresh` adds the `check` target and the line that runs it, and never
rewrites anything else in the Makefile:

```bash
d2w fhir init --refresh
make build
```

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
terminology validation for an offline build, and a generated guide does
build that way - a district registry in 51 seconds, site and all. What it
costs is one error per organisation unit carrying geometry: the GeoJSON
boundary attachment states its media type, that field binds to the IETF BCP
13 media types, and only a terminology server can answer that value set.
Those errors are the whole difference, and they go away online.

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
# bytes available to the docker VM
docker info --format '{{.MemTotal}}'

# a smaller heap, when you cannot raise the VM - the -Xmx flag is the knob
docker run --rm -v $(pwd)/ig:/home/publisher/ig -v fhir-ig-cache:/home/publisher/.fhir \
    fhir-ig \
    java -Xmx2g -jar /home/publisher/.ig-publisher/publisher.jar ig.ini -ig . -tx http://tx.fhir.org
```

Raising the VM's memory is the better fix either way; confirm a suspected OOM
kill by dropping
`--rm` from the run and then
`docker inspect <container> --format '{{.State.OOMKilled}}'`.

The other memory failure is the opposite one - the heap itself too small.
A national-scale guide (8,000-plus publishable files) does not fit the
default heap: the run dies mid-validation with
`Exception in thread "main" java.lang.OutOfMemoryError: Java heap space`
and a Java stack trace, which is a real build error, not a kill. The fix
is `make build JAVA_HEAP=8g`. The two knobs squeeze against each other
through the heap-plus-2-gigabyte rule: on one 16 GB docker VM, measured on
one national guide, `4g` dies in validation, `10g` clears validation and
is then OOM-killed at Jekyll, and `8g` completes the whole build - about
21 minutes, site, package, and QA report.

## Size the build

The counts below were taken from real instances (the Sierra Leone demo:
171 option sets, 2,664 registry instances, 3,101 resources; the uncapped
Lao national instance: 235 option sets, 25,162 registry instances). Counts
travel between machines; the wall clock they cost does not, so this section
talks about what is expensive relative to what.

Generation is the cheap half; the toolchain is where the time goes. On the
demo, `generate` and `validate` are both quick; a national instance takes
several minutes to generate and still costs a small fraction of a build.

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
resource - so the registry sets the wall clock of the publisher run, and
`[generate.organisation_units]` `max_level` / `root` is the lever on the
*published* size (25,162 instances down to 4,698 with `max_level = 4`), not
on the compile.

**What the compile costs** - running SUSHI on its own, with no publisher and
no timeout, isolates the compile. What it buys is the FSH: the forms and five
compiled CodeSystems, dominated by the two data-dictionary files (2.5MB of
FSH on the uncapped Lao IG). Writing that instance's 235 option sets as FSH
instead of predefined JSON makes the compile roughly half again as long,
which is the case for predefined terminology; fewer selected forms mean
smaller dictionary files. Docker is not where the compile's time goes - the
mount is a rounding error against it, and running SUSHI natively rather than
containerised saves on the order of a fifth. The rest is SUSHI's own work.
The publisher run is the other story entirely, and the section below is it.

**What the publisher pays for** is sheer resource count - every format it
writes and every page it renders is per resource - which is why the
scaffolded `sushi-config.yaml` excludes what a DHIS2-derived guide's
consumers never read: the XML and Turtle wire formats (`excludexml`,
`excludettl` - on the demo, half the output: 13,710 files and 466MB instead
of 26,120 and 874MB). The per-resource spreadsheet pass is not worth
excluding and there is no parameter for it anyway: the publisher knows no
`excludexls`, and on a national guide the pass it looks like it would skip
runs in under two seconds.

Terminology service time is a fixed cost only while the cache is warm: a
cold cache on a large guide pays `TX_SERVER` a round-trip per coding, which
can dominate everything else - and is why the caches survive a
`make refresh`.

## Why a build is fast now

A build that used to run for a long stretch was mostly not running. Two of
its longest phases were waiting, and a third was writing through a mount.
All three are handled by what `d2w fhir generate` emits and what
`d2w fhir init --refresh` writes, so a current project pays none of them.
The numbers below are one district-scale guide, measured phase by phase off
the publisher's own log.

**The terminology wait.** A DHIS2 identifier namespace -
`http://dhis2.org/fhir/id/option`, and five siblings - is declared as a
NamingSystem, which says the URL identifies DHIS2 objects and lists nothing.
Every ConceptMap row is validated against the system its target code sits
in, and a NamingSystem answers no `$validate-code`, so the publisher asked
the terminology server about each row on its own and was told
UNKNOWN_CODESYSTEM each time: **4,779 requests**, 57 percent of them byte-for-byte
repeats, with the narrative phase alone at **438 seconds**. Generation now
publishes each of those namespaces a second time, as a CodeSystem at the
same URL with `content: complete` and every identifier the guide's maps name
enumerated in it. The publisher answers the question out of the guide:
**5 requests, and narratives in 1.5 seconds**. (`content: not-present` does not
work - the publisher reads it as "the codes are elsewhere" and asks the
server anyway.)

Each of those CodeSystems is published at a URL outside the IG's own
canonical, which the publisher calls a mismatch unless the URL is declared.
The scaffolded `sushi-config.yaml` declares all six under `special-url`;
they follow `[generate] identifier_system_base`, so a project that changes
that key changes those six lines with it.

**The mount.** Docker on macOS reaches a host directory over a network-style
filesystem, and the publisher's output phase writes tens of thousands of
small files one at a time. That single phase took **341 seconds** through the
mount and **21 seconds** on the container's own disk. `make build` now streams
the project into the container, builds it there, and streams `output/`,
`fsh-generated/` and `input-cache/` back - two bulk copies instead of one
file at a time. `temp/` and `template/` stay behind; nothing reads them and
they are the bulk of what a build writes. `make build-bind` is the old
behaviour, worth reaching for when you want to watch `output/` fill up as it
is written.

**Offline builds work.** `make build TX_SERVER=n/a` completes - site, QA
report and all - in **51 seconds** on that guide. The section above says what it
costs.

## Keep the caches warm

Most of what a repeat build would re-pay is cached, and the scaffold wires
both up:

- **The FHIR package cache** is the named docker volume `fhir-ig-cache`,
  mounted at `~/.fhir` in the container by both runs above - which is why
  both need the chown, a fresh volume being root-owned and the publisher's
  user not. Without the volume, every run re-downloads the core packages
  before it can start, and on a slow link that download alone can rival the
  build.
- **The terminology cache** is `ig/input-cache/`, written by the publisher
  and ignored by git. Leave it in place when you clear build output; a warm
  tx cache takes the validation phase from minutes to seconds.

Both caches survive `make clean` and `make refresh` - a refresh pulls new
tooling and regenerates, neither of which invalidates a cache keyed by what
it holds. `make clean-all` is the deliberate wipe, and running it before a
build is how you reproduce a cold one.

## Publish it

The generated site lands in `ig/output/` - plain static files. Publish them
however your organisation hosts static sites; the canonical URL you
scaffolded with is where consumers will expect to find it. Before handing
it over, read `ig/output/qa.html` - the publisher's own QA summary of
errors, warnings, and broken links.

Next: [Serve the guide](201-serve.md) - the compiled guide, answered live as a
FHIR endpoint.
