# ffman: one command model, in Python

**Status: ready; D1–D4 adopted as recommended (§9), revisable on request.**
This is the guide for the
refactor: what ffman becomes, how it is built, and the gates that keep it from
regressing or leaving dead code. Decisions and their evidence stay in
[`07-tools.md`](decisions.md); this file is the procedure.

## 1. Why

- **The subcommands are one operation.** `resize`, `overlay`, `attach` and
  `convert` share most options (`parse_shared`). They differ only in whether
  the video is re-encoded (`attach` copies) and how (lossless in the source's
  codec, or a delivery preset). Every feature had to be wired into several of
  them: the effects went into `cmd_resize` and `cmd_overlay` separately,
  across five ffmpeg call sites.
- **The surface is inconsistent.** The input is `--input`, `--input-video` or
  `--input-media`. The default output is `-resized`, `-subtitled`,
  `-youtube.mp4` or *in place*. `--input-subs` burns subtitles in `overlay`
  and adds a track in `attach`.
- **Bash is past its limit.** 1,848 lines, 86 functions and 26 embedded awk
  programs (the ASS renderer among them). Google's Shell Style Guide says to
  rewrite past 100 lines or "non-straightforward control flow". Several
  defects in this project were bash-specific:
  - `$((oext != gif))` compared a variable named `gif`;
  - `local start` unset under `set -u`;
  - a persistent `RETURN` trap;
  - word-split arrays (SC2207);
  - filter labels read as array subscripts (SC1087);
  - input indices counted by hand (`DITHIN`, `MOSHIN`, `VSRC`).
- **The default encode is a usability defect.** `resize` re-encodes
  losslessly. A 720p H.264 MP4 resized to 640 wide came out **larger**
  (2.68 MB against 2.54 MB) and in *High 4:4:4 Predictive*, which most phones,
  browsers and hardware decoders cannot play.

## 2. Review of the first proposal

What changed after reviewing it end to end:

| First proposal | Problem | Now |
|---|---|---|
| `--add-subs FILE[:LANG]` | `:` is legal in paths | `--add-subs FILE`, repeatable; the language from `--language`, one per `--add-subs` in order (a count mismatch is refused); in stage B also from the file (whisper JSON `result.language`, a `name.por.srt` suffix) |
| `--attach FILE` | clashes with "attach subtitles" | `--attachment FILE` (Matroska attachments: fonts, and so on) and `--cover IMAGE` |
| Default output unstated | four rules today, one of them destructive | `STEM.ffman.EXT` beside the input; replacing it needs an explicit `--in-place` |
| Port, then change defaults | a regression and an intended change would look alike | Two stages. **A**: processing equivalence -- Python makes the same ffmpeg calls, side files and outputs as bash; the new CLI surface (commands, flags, default names, messages) exists from the start. **B**: intended processing changes, each with its own test and changelog entry |
| Tests "ported" | no proof that none was lost | A traceability ledger: every old check maps to a pytest id (§8, G5) |
| Two type checkers | double noise; ty is unstable | basedpyright blocks; ty is advisory (§6) |
| No way to inspect a plan | tests must render to see decisions | `--dry-run` prints the plan and the ffmpeg commands. It is a feature, and the cheapest test oracle |
| A flag per effect | with audio effects, 25+ effect flags among ~30 real options; name clashes (a "blur" or "noise" in video and audio; `--blur` next to `--bblur`); parameters as global flags (`--date`, `--time`) | `--vfx NAME[:ARGS]` and `--afx NAME[:ARGS]`, repeatable, drawn from a registry; `ffman effects` shows the catalogue (§3.3) |

Kept after review:

- **Explicit `concat`.** Guessing from the input count is ambiguous, because
  subtitles, attachments and palettes are inputs too.
- **A fixed effect order.** It follows physics: picture, lens and film, tape,
  subtitles, display. Letting users reorder it would reintroduce errors the
  reviews removed.
- **No ffmpeg-like DSL.** It would rebuild ffmpeg's complexity, when ffman's
  value is proven defaults.

## 3. The command model

### 3.1 Commands

| Command | Job | Inputs, outputs |
|---|---|---|
| `convert` | transform one media file | 1 media, plus side files (subtitles, attachments) → 1 media |
| `concat` | join files end to end | N media → 1 media (then everything `convert` does) |
| `transcribe` | speech to subtitles (whisper.cpp) | 1 media → a transcript (srt, vtt, json) |
| `probe` *(later)* | what ffman sees in a file | 1 media → a report |
| `effects` | the catalogue: effects, parameters, auto values | none → a listing (from the registry) |

Global options: `-y/--overwrite`, `--dry-run`, `--help`, `--version`; `-v/--verbose` in stage B, once it has a meaning (ffman-spec §1).

### 3.2 `convert` options

| Group | Options |
|---|---|
| I/O | `-i/--input FILE`, `-o/--output FILE` (default `STEM.ffman.EXT`), `--in-place` |
| Picture | `-w/--width`, `-H/--height`, `-a/--aspect-ratio`, `-r/--resize-mode fit\|cover\|stretch`, `-b/--bblur [SIGMA]` |
| Video effects | `--vfx NAME[:ARGS]`, repeatable (§3.3) |
| Burned subtitles | `--burn-subs FILE`, `--overlay-mode`, `--highlight-mode`, `-f/--font`, `--font-size`, `--margin-bottom` |
| Soft subtitles | `--add-subs FILE` (repeatable), `--language CODE` (repeatable) |
| Metadata | `--title`, `--metadata KEY=VALUE` (repeatable), `--attachment FILE`, `--cover IMAGE` |
| Encoding | `--preset youtube`, `--video-codec`, `--audio-codec`, `--lossless`, `--crf N` |
| Audio | `--normalize`; audio effects: `--afx NAME[:ARGS]`, repeatable (§3.3) |
| GIF | chosen by a `.gif` output; `--loop`, `--loop-reverse` |

### 3.3 Effects

**One option per domain; the effects live in a registry, not the option
space.** `--vfx` takes video effects, `--afx` audio ones; repeat the option
for more. `--help` names the two options. `ffman effects [video|audio]
[NAME]` prints the catalogue: parameters, types, ranges, auto values. Both
are generated from the registry that also parses and validates.

```
SPEC  := NAME [ ":" ARGS ]
ARGS  := ARG ( "," ARG )*
ARG   := VALUE            first argument only: the main parameter
       | KEY "=" VALUE
```

- **Unambiguous:** only the first `:` ends the name, only `,` separates
  arguments, and only the first `=` ends a key. Values may contain `:` and
  `=` (`time=23:59:58`, `date=1999:12:31`). No value needs `,` or a space,
  so nothing needs quoting.
- **No value means auto:** `blur` is auto, `blur:8` is sigma 8. The same
  rules as today's optional values.
- **Order is the physics', not the listing's.** Naming an effect twice is
  refused. So is an unknown name, key or value, with the valid ones listed.
- **Video catalogue (from today's flags):** `blur[:sigma]`, `pixelate[:size]`,
  `invert`, `chromatic-aberration[:px]`, `halation`,
  `camcorder[:date=…,time=…]`, `datamosh[:seconds]`, `vhs`, `dither[:colours]`,
  `crt`.
- **Not effects:** bar blur (`-b/--bblur`) is framing, and stays with the
  resize options. Burned subtitles, GIF looping and normalisation are
  outputs, not effects.
- **Later, a thin layer:** `--look NAME` presets spanning both domains
  (`vhs`: the picture plus linear-track audio), defined in the same registry.

### 3.4 Rules

1. **Copy or encode, per stream.** A stream no option touches is copied
   (`attach`'s old guarantee, now general). Anything else is encoded under the
   chosen policy. The container must accept each copied stream, or it is
   encoded instead, and a note on stderr (and the plan) says so.
2. **Encode options never override each other; contradictions are refused.**
   `--preset` excludes `--lossless`, `--crf`, `--video-codec` and
   `--audio-codec`. `--lossless` excludes `--crf`. `--video-codec` combines
   with either. `--crf` is validated against the codec's own range. Without
   any of them, the default policy applies (D2).
3. **Fixed stage order:** picture → lens and film → camcorder → tape →
   subtitles → display (dither, CRT). Datamosh is its own pass after lens and
   film.
4. **Refuse nonsense early:** effects with `--lossless` into GIF, `--loop` on
   a still image, `--vfx datamosh` on a still image, `--in-place` together with
   `-o`, a `--language` count mismatch.
5. **`--dry-run` prints** the plan (per stream: copy or encode, and why) and
   every ffmpeg command. The read-only analyses run (probe, bar detection,
   scene cuts), because the commands depend on them. Generated side files
   (ASS) go to a temp dir that is removed. No output is written.

### 3.5 Examples

```sh
# Resize for Stories, blurred bars, delivery encode (the default)
ffman convert -i trip.mp4 -a 9:16 -w 1080 -b -o trip.story.mp4

# Burn word-highlighted subtitles from a whisper transcript
ffman convert -i talk.mp4 --burn-subs talk.json --overlay-mode word-highlight

# Add two soft subtitle tracks: no re-encode, nothing else changes
ffman convert -i film.mkv --add-subs film.por.srt --add-subs film.eng.srt -o film.subs.mkv

# The same, in place, with explicit languages
ffman convert -i film.mkv --add-subs a.srt --language por --add-subs b.srt --language eng --in-place

# A looping, reversing GIF of a clip, with the VHS look
ffman convert -i clip.mov -w 480 --vfx vhs -o clip.gif --loop-reverse

# Several effects: listed in any order, applied in the physical order
ffman convert -i home.mp4 --vfx crt --vfx vhs --vfx camcorder:date=1999-12-31,time=23:59:58

# An effect with its value, and an audio effect (phase 7)
ffman convert -i song.mp4 --vfx blur:8 --afx reverb:hall

# The catalogue
ffman effects video
ffman effects camcorder

# YouTube delivery, loudness normalised
ffman convert -i edit.mov --preset youtube --normalize -o edit.yt.mp4

# Lossless, for an intermediate
ffman convert -i scan.mkv -w 1920 --lossless -o scan.1080.mkv

# Transcribe, then burn: two jobs, two commands
ffman transcribe -i talk.mp4 -o talk.json --model ~/models/ggml-large-v3.bin
ffman convert -i talk.mp4 --burn-subs talk.json -o talk.subbed.mp4

# Join clips, then shape them in the same run
ffman concat -i a.mp4 -i b.mp4 -i c.mp4 -a 1:1 -w 1080 -o abc.square.mp4

# See what would happen
ffman convert -i trip.mp4 -a 9:16 -b --vfx crt --dry-run
```

### 3.6 Migration (the old commands and flags refuse, printing the equivalent)

| Old | New |
|---|---|
| `ffman resize -i F …` | `ffman convert -i F …` (lossless in stage A, as now; D2's delivery default in stage B; `--lossless` keeps it) |
| `ffman overlay -i F --input-subs S …` | `ffman convert -i F --burn-subs S …` |
| `ffman attach -i F --input-subs S -l L` | `ffman convert -i F --add-subs S --language L --in-place` |
| `ffman convert -i F -p yt` | unchanged |
| `--vhs`, `--blur 8`, `--dither` … | `--vfx vhs`, `--vfx blur:8`, `--vfx dither` … |
| `--camcorder --date D --time T` | `--vfx camcorder:date=D,time=T` |
| default output `-resized` / `-subtitled` / `-youtube` | `STEM.ffman.EXT` |

## 4. Architecture

What exists (phase 1), and what the later phases add (marked):

```
tools/ffman/
  pyproject.toml            hatchling; ruff, basedpyright, pytest, coverage config
  src/ffman/
    __main__.py  cli.py     the top level; COMMANDS; old commands refused
    options.py              THE option registry (spellings, arity, empty-value
                            rule, help, group) and its parser -- not argparse,
                            which cannot keep the spec's messages; MIGRATED
    errors.py               FfmanError (exit 1) and refuse(); nothing else exits
                            but run.Interrupted (signals: 128 + n)
    checks.py               bash's value checks (is_uint, is_num, SAFE_PATH)
    fmt.py                  awk_print: numbers as the bash ffman's awk printed them
    output.py               the output path, and the partial file it becomes
    run.py                  children, signals, the work directory, thread
                            arguments, --dry-run
    effects/                the registry: each effect's stage and parameters
                            (range, auto rule); parses SPECs, generates
                            `ffman effects`. Phase 3: each effect's build(graph, ...)
    jobs/convert_options.py convert's options, validated and typed
    phase 2: probe.py (ffprobe JSON -> dataclasses), geometry.py (Fractions:
             SAR, rotation, size), plan.py (per stream: copy|encode, why),
             graph.py (nodes, labels, escaping), encode.py (a table), light.py
    phase 3: resize.py (fit, cover, stretch, the bar blur), jobs/convert.py
             (the job, in its bash command's order), subs/ (ingest, layout, ass),
             passes.py (palette, datamosh); phase 7: concat.py, transcribe.py
  tests/                    §7; tests/equivalence/: the bash comparison (stage A)
```

Principles:

- **Functional core, imperative shell.** `probe → plan → graph → argv` are
  pure functions of data, testable without ffmpeg. Only `run.py` executes
  anything.
- **One source of truth for each concern:**
  - options: `options.py` parses, and generates `--help` and the migration
    errors (the effects' from the effects registry);
  - effects: the effects registry parses `--vfx`/`--afx`, validates, and
    generates `ffman effects`;
  - encoders: one table;
  - effect order: stage enums;
  - filter labels and escaping: `graph.py` only, which removes the SC1087
    class of bug;
  - transfer curves: `light.py`;
  - thread arguments: `run.py`, from `nproc` itself: coreutils 9.11 (the
    pin) honours OMP_NUM_THREADS, OMP_THREAD_LIMIT and cgroup v2 CPU quotas
    besides affinity, which `os.process_cpu_count()` does not (gnulib
    `nproc.c` at coreutils' pinned commit).
- **Exact arithmetic.** SAR, frame rates and time bases are `Fraction`s,
  never floats; floats appear only where a filter takes one. Where bash's
  awk arithmetic (doubles, `%.6g` between steps) gave a different answer, the
  exact one is a proven correction (G4) -- as for sizes (`geometry.py`) -- or,
  where only the text of a number differs, the text is bash's (`fmt.py`, stage A's
  scaffolding: phase 6 replaces it with exact arithmetic).
- **Constants carry provenance.** Every measured or sourced number (VHS
  906/90.6/1811, CRT σ 0.02–0.3, bar blur's 34.6) is a named constant, with a
  one-line source and a pointer to the `07-tools.md` row.
- **Runtime uses the standard library only**: `json`,
  `subprocess`, `dataclasses`, `fractions`, `pathlib`, `tempfile`, `signal`.
  NumPy stays in the tests.
- **Types are complete.** Public functions are fully annotated, and `Any` is
  forbidden outside the JSON boundary (`probe.py`, `subs/ingest.py`), where it
  is narrowed immediately.

## 5. Nix

- `pkgs/default.nix`: `ffman = python3Packages.buildPythonApplication {
  pyproject = true; build-system = [ hatchling ]; … }`. `makeWrapper
  --set PATH` (not `--prefix`: what `inheritPath = false` is for the bash
  tools) to `ffmanRuntime`, which is `ffmanTools` without the text tools
  Python replaces. It keeps `ffmanEnv` (`FFMAN_FONTS_DIR`). `requires-python
  >= 3.13` (the pin's Python).
- **Checks** in `nix flake check` (the equivalence harness is a separate,
  explicit derivation: `nix build .#ffman-equivalence` -- a package, which
  `nix flake check` evaluates and does not build; it fails unless every
  invocation of both suites is the same, and keeps the reports):

  | Check | Runs |
  |---|---|
  | `ffman-lint` | `ruff check`, `ruff format --check`, `vulture` (the product: `[tool.vulture]`) |
  | `ffman-types` | `basedpyright` |
  | `ffman-tests` | pytest: unit, integration, property (not `slow`) |
  | `ffman-matrix` | pytest `-m slow` with `-n auto` |

- The dev shell adds `ruff`, `basedpyright`, `ty` and the test Python.
- During stage A both existed: `ffman` the bash one (the installed product),
  and the Python one `ffman-next`, built and checked but installed nowhere.
  Phase 5 switched them: `ffman` is the Python package, `ffman-next` is gone,
  and the bash suite runs as `ffman-bash-tests` until the bash one is deleted.

## 6. Tooling

| Tool | Role | Configuration |
|---|---|---|
| **ruff** 0.15 | lint and format; blocks | `select = ["ALL"]` (pydocstyle `convention = "google"`: docstrings on public modules, classes and functions, short, per this repo's rule), minus what conflicts with the formatter (`COM812`, `ISC001`) and justified per-file ignores (`T201` in `cli.py`; `S603`/`S607` in `run.py`, where subprocess is the point). The pin controls upgrades, so `ALL` cannot drift |
| **basedpyright** 1.39 | type checker; **blocks** | `typeCheckingMode = "all"` (every rule an error; verified against 1.39.3), `failOnWarnings`, no `# type: ignore` without an error code and a reason |
| **ty** 0.0.38 | type checker; **advisory** | run in the dev shell and CI, never failing the build. It is beta with no stable diagnostics ("breaking changes … between any two versions"), and the pin lags upstream (0.0.80+). Promote it when 1.0 is in the pin and it runs clean |
| pytest 9, pytest-xdist, pytest-timeout | test runner | `--strict-markers`, markers `slow`, `ffmpeg`, `equivalence`; a timeout per test |
| hypothesis 6.151 | property tests | replaces `fuzz.py` |
| pytest-cov / coverage | branch coverage | ≥ 95% on `src/ffman`; every `# pragma: no cover` has a reason |
| vulture 2.14 | dead code | zero findings at the end (G6) |
| syrupy 5.1 | snapshots | only for generated ASS text and `--help`; never for argv |

## 7. Tests: from bash to pytest

**Yes, they move to pytest.** The bash runners exist only because ffman was
bash. `check.py` and `fuzz.py` are already Python.

| Layer | What | Source |
|---|---|---|
| unit | pure functions: registry, geometry, planner, graph builder, light LUTs, effect builders, layout and wrap, ASS text | new, plus logic now tested indirectly |
| integration (`ffmpeg`) | the CLI black box: render, measure | `run.sh`'s 204 check sites (289 checks) |
| matrix (`slow`) | combinations, parametrised with ids like `M11-vhs-gif` | `matrix.sh`'s 754 cases |
| property | Hypothesis: transcripts, bar positions, sizes, option combinations → invariants (lines on screen, exact line count, argv well-formed); SPEC grammar round-trips (render(parse(s)) == s), and every invalid SPEC is refused with a message | `fuzz.py`, new |
| equivalence (stage A only) | bash vs Python on the same inputs (G1, G2) | new; deleted with bash |

Measurement helpers (`fx_prop`, edge width, light, `vmd5`) become one
`tests/support/measure.py`, used through fixtures. Fixtures move to
`tests/fixtures/`, unchanged.

## 8. Gates: no regressions, no stale code

- **G1, call equivalence.** For every invocation in the corpus (derived from
  `run.sh` and `matrix.sh`, mapped to the new CLI by the test adapter),
  compared **live** against the bash `ffman` in the same environment (no stored
  oracle: encoder detection depends on it): the ffmpeg commands (recorded by
  the argument shim) and the generated side files (ASS text) must be equal,
  after canonicalising temp paths, and filtergraphs as ffmpeg parses them
  (tests/support/filtergraph.py, proven against ffmpeg: bash quoted some
  values by hand, graph.py escapes all one way -- different texts, the same
  graph) with link labels, and -map's references to them, renamed by first
  appearance. A graph the parser cannot read is counted, never passed. Stage A therefore reproduces bash's argument order and
  number formatting (one formatting helper, matching awk's `printf`).
  Where an invocation leaves the camcorder's clock to the run (no --date and
  --time: 12 in the corpus), only its commands are compared -- its stamp, and
  what is drawn after it, follow the time of the run; the stamp's text is
  proven equal to bash's for any clock apart (tests/equivalence: cam_prepare's,
  300 cases in 3 time zones).
- **G2, output equivalence**, where argv legitimately differs. Decoded
  frame MD5s, stream parameters, container metadata, subtitle payloads and
  durations must be equal.
- **G3, suites.** The pytest ports of the 289 suite checks, the 754 matrix
  cases and the properties all pass against Python.
- **G4, intended changes only in stage B -- except proven corrections.** Each
  has a changelog line (`tools/ffman/CHANGELOG.md`), a test that fails on stage
  A's behaviour, and a `07-tools.md` row. A correction may land in stage A when
  it is *proven*: bash's answer shown wrong against a stated rule (its own
  documented one), on a measured set, the new answer never wrong on it; and
  the bash comparison restated to accept a difference only where bash breaks
  that rule, keeping every other difference a failure. Changes that no such
  predicate can separate from a regression (a new look, a new default) wait
  for stage B.
- **G5, nothing lost.** A ledger gives each old check a state: *mapped*
  (its pytest id), *surface* (the same behaviour through the new CLI, with a
  new message or name), or *changed* (stage B, with the reason), in
  `tools/ffman/migration/LEDGER.md`. Example: `S123 → test_blur::test_light_kept`. Phase 5 deletes the old runners
  only when every row has one. The ledger is a migration artefact, deleted
  with them.
- **G6, nothing stale:**
  - every function in the Appendix is either ported or dropped with a reason;
  - `rg -n "ffman\.sh|ffman-tests/|run\.sh|matrix\.sh|cmd_(resize|overlay|attach)"`
    returns only history;
  - vulture reports zero; coverage ≥ 95%; no `TODO`/`FIXME` or commented-out
    code (ruff `TD`, `FIX`, `ERA`);
  - `07-tools.md`, the run-book and `AGENTS.md` refer to Python modules, not
    bash functions.

## 9. Decisions (adopted as recommended, in bold; revisable)

- **D1, command model:** **`convert` + `concat` + `transcribe`** (and `probe`
  later), or keep the four commands.
- **D2, default encode (stage B):** **a delivery default** (H.264 High,
  yuv420p, CRF 18, for `.mp4`; per-container defaults for `.webm`/`.mkv`)
  with `--lossless` explicit, or keep lossless as the default.
- **D3, language:** **Python**, or Rust (§1).
- **D4, old commands:** **refuse and print the equivalent**, or alias them.
- **D5, build backend:** **hatchling**, or uv's `uv_build`. Recorded late (it
  had been chosen in phase 1 without a reason). Both build this project -- pure
  Python, a static version, no hooks. uv's docs advise capping `uv_build`
  below the next minor (minors may break), and the pin carries uv 0.11.21 but
  uv-build 0.10.0: a cap out of step with the dev shell's uv, or none against
  that advice. Hatchling (1.29.0, PyPA's Hatch) has neither. uv's strengths
  (locking, resolving, environments) are Nix's here. Bytecode is neither's
  concern: a build backend leaves it out of the wheel (hatchling 1.29.0's only
  bytecode code excludes `__pycache__`; `uv_build` excludes it by default),
  and the installer compiles it -- uv's `compile-bytecode` is an installer
  setting, off by default. Here the installer is nixpkgs' (`python -m
  installer`, 1.0.0, whose default compiles levels 0 and 1; nixpkgs' one patch
  adds `--executable`): ffman's 29 modules install with 58 `.pyc`, which a
  read-only store needs, as Python cannot cache there.

## 10. Checklist

**Nix in a restricted sandbox** (no binary cache): nix-portable from its
GitHub releases, `NP_GIT=/usr/bin/git` (else it builds git from source),
`NIX_SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt` (the proxy's CA),
`--option substituters ''`. It evaluates (drvPaths, `nix derivation show`,
before/after comparisons at a `git+file://…?rev=` URL); it cannot build.
The local Python toolchain matches the pin exactly (Python 3.13 via uv; ruff,
basedpyright, ty, pytest, pytest-cov, pytest-timeout and coverage at the
pin's versions) -- a coverage left to pip's choice (7.16 for the pin's 7.14)
once made a local gate differ from the Nix one. And the tests run as Nix runs
them, the environment emptied (`env -i PATH=... HOME=/homeless-shelter
TMPDIR=/tmp`): this sandbox sets PYTHONUNBUFFERED, which hid a broken-pipe
bug that only buffered output shows (the owner's build found it).

Working rules for every phase: one checklist item per commit (or less);
every commit leaves `nix flake check` green, with the installed `ffman`
unchanged until phase 5; a verified tarball at the end of each session;
docs (§4's provenance, `07-tools.md`) updated in the same commit as the code.

**Phase 0: spec and baseline** (no product code)
- [x] Record D1–D4.
- [x] Freeze the §3 spec: every option with type, default, validator and help ([`ffman-spec.md`](ffman-spec.md)).
- [x] Tag the bash baseline (`ffman-bash-final`).
- [x] Generate the corpus: every invocation in `run.sh`/`matrix.sh`, as old-CLI argv (`tools/ffman/migration/corpus.jsonl`: 896 distinct, from `make-corpus.sh`).
- [x] Create the ledger with all 289 + 754 old checks, target column empty (`tools/ffman/migration/LEDGER.md`; the 33 M8 cases test an internal function and map to unit tests).
- [x] Fill the Appendix's target column (module or "dropped: reason").

**Phase 1: skeleton**
- [x] `tools/ffman/` layout; `pyproject.toml` with ruff, basedpyright and pytest configuration.
- [x] Nix: `ffman-next` (Python) beside `ffman` (bash); the checks (lint, types, suite; the matrix check arrives with the first slow test); `nix develop .#ffman`. *Built on the owner's machine: 205 passed, types and lint clean (`nix build .#checks.x86_64-linux.ffman-next-{tests,lint,types}`); that build showed run.py at 83% where the sandbox had 100% -- the child's coverage hook is a site `.pth`, which a Nix PYTHONPATH does not process; fixed (c399a33).*
- [x] Confirm basedpyright's preset names and `failOnWarnings` against 1.39; set the strictest (asked of 1.39.3 itself: `strict`, `recommended`, `all` accepted, an invalid mode exit 3, `failOnWarnings` fails warnings, unknown settings reported; `all` chosen).
- [x] `options.py` registry and parser (argparse replaced: its messages could not keep the spec's) → `--help` generated; migration errors for commands and flags (D4); `convert`'s options validated and typed (`jobs/convert_options.py`); `fmt.awk_print` (checked against gawk).
- [x] Output resolution: the `STEM.ffman.EXT` default, `--in-place`, `--overwrite`, the same-file rule, the partial file (`output.py`; `ext_of` and `same_file` cross-checked against bash's on edge cases).
- [x] The effects registry and SPEC parser (`--vfx`; `--afx` arrives with the first audio effect, phase 7); `ffman effects` generated; old effect flags refuse with their `--vfx` form (`effects/__init__.py`, `checks.py`; validators cross-checked against bash's `fx_validate`).
- [x] `errors.py`, `run.py` (signals, temp dirs, threads, `--dry-run`): `ffargs` cross-checked against bash's (35 cases); signals proven on real process trees (status, the tree gone, the KILL after 3 s, the work directory and partial removed).
- [x] The equivalence harness (`tests/equivalence/`, marked `equivalence`): the old-to-new CLI adapter, the argument shim, and a dual `$FFMAN` (`ffman-dual`) that runs bash (what the suite sees) and Python (to scratch) on the suites' own invocations and inputs (G1: producing commands and side files, canonicalised; G2: every stream's packet CRCs and properties); `summary.py` sums a report up. Validated by bash against itself -- run.sh 289/289 and matrix.sh 754/754 through it, no difference -- and against a bash with one line changed (blur steps=6 -> 5): its 5 `--blur` invocations caught, nothing else. *Measured on the way: container bytes vary run to run (Matroska's UID and date), so media is compared by packets; the camcorder stamps the time of the run where no --date and --time are given, and so does everything drawn after it (a dither palette), so those compare commands only; the suites' own fakes and recorders sit on PATH, so the shim runs the next tool on the PATH of the moment, bash runs first, and the small files the new side touched are restored and listed.*
  *For phase 3:* where the new surface changes what is accepted, the comparison differs by design -- the old `convert` required `--preset`, the new one does not -- so the summary will need those cases classified as expected, each with its reason, before the corpus slices are counted.
- [x] The checks green on the owner's machine (the three built alone: the whole `nix flake check` runs out of memory there, evaluating every host).
- [x] Phase 1 reviewed end to end (every file, passes as efficient-code-review), each finding shown on bash or by a probe, then fixed with a test that fails without the fix: empty values as bash treated each option (17 probed: unset, validated, or kept -- 12 had differed); the effect flags' migration messages from the effects registry (5 had suggested refused syntax); --in-place's extension check; captured output decoded as jq did (hardening: a stray byte would crash the decode; ffmpeg 8.1.2 and ffprobe escape invalid UTF-8 themselves, probed, so no caller today could); a reader gone is 141 and silent, as bash; invert described in RGB; gawk's +inf/-nan; datamosh's stage confirmed after the lens and film (bash's intermediate carries them); the architecture section rewritten to what exists.

**Phase 2: the pure core**
- [x] `probe.py` dataclasses, from recorded ffprobe JSON (fixtures): the fields bash's `pq` read, through its VSEL and ASEL, as it read them (absent, null or empty: None; text stays text); nine files made by `tests/fixtures/probe/record.sh` (ffprobe 8.1.2 required); every field equal to bash's own `pq` on every fixture (the equivalence oracle); a mutation of each selection rule caught. `read()` takes a `Capturing` protocol, not the runner. The format's `duration` added later: bash reads it unquoted (`pq .format.duration`: camcorder, bar detection, attach), which the first inventory's pattern (quoted queries only) missed; a complete search found no other field, and `probe()` is bash's only ffprobe.
- [x] `geometry.py`: SAR, rotation, target size -- bash's `geometry` and `plan_dimensions`, its rules computed exactly, a proven correction (G4): on 1 M realistic requests bash broke its documented rule 2103 times (sizes 2 px off from double rounding, ties rounded down, refusals at exactly 1 px), exact arithmetic never (3 M cases). The oracle: Python equals the rule, written independently, on 14,256 target cases; bash differs in exactly 33, each where bash breaks the rule; a mutant (ties down) fails it; 780 display cases equal. Unit cases are bash's answers (one tie corrected) plus the corrections, which fail on bash's arithmetic; exact Hypothesis properties (6.151.10). `parse_aspect` lives here: the CLI validates with the domain's rule.
- [x] `graph.py`: nodes, labels, escaping; property: every graph parses under `ffmpeg -filter_complex … -f null`. One escaper at ffmpeg's two levels (filters.texi, av_get_token, ff_filter_opt_parse at n8.1.2); proven against ffmpeg: any value reaches it unchanged (the metadata filter prints it back), a parser transcribed from its source reads what it reads (random texts, bash's quoted forms, and its refusals), every graph built runs; three escaper mutants fail the properties (once the alphabets drew the special characters: uniform unicode never did). Refused at build: an empty positional value (ffmpeg drops it). The bash comparison (G1) compares graphs as ffmpeg parses them; re-validated (run.sh 289/289 and matrix.sh through it, 0 differ; the blur mutant caught), and its unparsed-graph count found a bug first: option keys had been limited to lowercase, refusing gblur's `sigmaV` -- keys now take ffmpeg's alphabet (`is_key_char`), and so does the property's strategy (it had drawn lowercase only, as the code assumed); filter names checked against all 479 of ffmpeg 8.1.2's.
- [x] `plan.py`: copy or encode per stream; the rules in §3.4. The flows (spec 3.8: a job does what one bash command did; what none did is refused, for now), and each flow's decisions -- small pure functions returning data, called by the job in its bash command's order. Picture and tracks: equal to bash's own functions (video_encoder 72 cases, audio_encoder 90, image_encoder, loop_check, family, sub_codec_for, carry_tracks 60). YouTube: equal to bash's convert run whole with its side effects stubbed (1050 picture cases -- colour paths, fields, rates, sizes -- and 72 sound and refusal cases), filters compared as ffmpeg parses them; exact fractions give bash's GOP on every rate (fps has 6 decimals: a tie at a half is exact in a double too). Mutants caught: FDK not preferred, channels defaulting to 1, GOP ties up, the higher bitrate from 30 or at 30.5 fps (these two survived until 30 and 61/2 joined the rates). `encode.py` began as the codec table they share with the option checks.
- [x] `encode.py` table, `light.py`. Every encoder named once, its settings bash's argument for argument; the builders take plain values (plan.py imports encode.py, not the reverse). light.py holds bash's curves raw (bash's `\,` was its filter text's; graph.py escapes). Equal to bash's own functions on grids: video_encoder with ffv1_slices 960 cases, audio_encoder through plan.sound 108, image, GIF, container flags, src_tb, light_luts 60, the optimisers; YouTube's whole x264 slice added to its oracle (1122 cases). Mutants caught: ffv1 without k = 2v, opus's ceiling for mono only, light's untagged without `unknown`. **Phase 2 done.** Reviewed end to end (efficient-code-review, efficient-reason): one Major found at a seam -- plan's copy/drop decisions carried no codec, which encode.audio_args needs, and the oracle had composed them from the option instead; now carried, and composed as the job will -- and three Minor: --loop ignored by the YouTube and tracks flows (now refused as their other picture options), the normalising note's `? ch` for 0 channels (bash printed 0; its grid lacked 0), and the MP4 family defined twice (now encode.py's alone). record.sh cleans up, and re-records every field probe reads.

**Phase 3: stage A port, feature by feature** (each item done = its corpus slice equal under G1 and G2, and its ledger rows stated)
- [x] resize and fit/cover/stretch; bar blur. `jobs/convert.py` (the job, in resize's order; a feature not ported yet is refused as `not ported yet: FEATURE`, which the harness counts apart, by feature), `resize.py` (equal to bash's resize_filter on 384 cases, 176 distinct graphs; four mutants caught), `graph.Open`, `encode.parse_encoders` (its legend is no encoder: 193 on 8.1.2). G1/G2 live: run.sh 289/289, matrix.sh 754/754 through the harness -- 0 differ; 160 resizes rendered by both, all equal; the rest not ported yet, none a resize. The harness's own bug, found by it: an adapted in-place job got bash's old *convert* (YouTube) default beside `--in-place` (the two CLIs share the name); fixed, tested. Ledger: 46 rows stated (tests/test_suite_resize.py, the suite's inputs and values; 3 surface). For phase 4: the measured rows S202, S203, S275, S287, and matrix M1/M3. The owner's build: the three checks green at 887f51b.
- [x] encoders, containers, carried tracks, the audio policy. The resize job's code, item 1's; this item's G1 slice from the same live run: every invocation choosing a codec that Python handles equal (50 rendered by both, 161 refused by both; the other 183 burn subtitles, their own item). Ported (tests/suite/test_encode.py): matrix M4, 56 codec x container cases (their ids checked against the ledger's titles), threads with nproc faked (S281-S285, the same thread options as bash's), SIGTERM (S104: 143, nothing reading, no partial, no work dir), a protocol-like name, the family notice; 66 rows stated. Three mutants caught, each by its port. The suite ports now live in tests/suite/ (shared fixtures; helpers in tests/support/media.py). The owner's build then failed one test: the M4-to-ledger check read migration/LEDGER.md, outside the Nix source (pyproject.toml, README.md, src, tests); the ledger's checks now live beside the harness (tests/equivalence/test_ledger.py: the M4 titles, and every stated row naming a collected test), and the Nix selection is run locally from exactly that source set, which reproduced the failure before the fix.
- [x] images, optimisers, GIF (palette, loop, loop-reverse). gif.py (bash's gif_chain, equal on all three loops; two mutants caught), plan.image_frame, the job's GIF and image paths, and each optimiser run on the partial before the rename (a failing one ends the job with a message: spec 3.7, surface). G1/G2 live: run.sh 289/289, matrix.sh 754/754, 0 differ; 47 image and GIF renders by both, all equal (the optimisers' calls compared too); none left unported. Ported: suite/test_images.py (S031-S035, S210-S219; references literals of bash's commands); 15 rows stated. Found on the way: a GIF test's frame count was my assumption, not the fixture's (its subtitle track shortens it: 22 frames) -- the rule 2n-2 now read from the clip itself; a PNG mutant equivalent (ffmpeg auto-selects rgb24 for rgb555le), a grayscale one caught. S210-S211 are the suite's weak claim (no jpegoptim would pass them too); G1 compares its call. plan.picture_encoding, GifFrames and the plan's Picture alias removed: only tests used them (the job asks lossless and image_frame), and Picture named resize.py's dataclass too.
- [x] effects: blur, pixelate, invert, chromatic aberration, halation, VHS, CRT (single pass). effects/filters.py (a builder an effect, applied in the registry's order -- bash's; chain(): the frame around the subtitles' place, null where bash wrote it, the source's format given back for a video codec, a clean refusal where the stream has none). Equal to bash's fx_chain on 1248 cases (13 effect sets x 4 frames x 3 SAR texts x head x restore x 2 pictures), and on the 3 inputs, searched for, where bash's text and the exact value round apart (blur's displayed width at SAR 32/27 from 2816 px; chromatic aberration's 2987x480 at 14): the text-chaining mutants survived the grid and fail these. bash's vhs_noise had a dead line (r - s > 1 cannot be: proof in the code); not ported. The job: effects without a size (the frame as stored, FX_SAR as bash wrote it: 1/1 kept). G1/G2 live: run.sh 289/289, matrix.sh 754/754, 0 differ; same 96 -> 118 and 416 -> 446; unported --vfx only dither, datamosh, camcorder. Ported (suite/test_effects.py): each effect's size, format and frames kept; no size needed; invert exact; a GIF frame's 256 colours; the refusals (surface); 14 rows stated, three mutants each caught. For phase 4 (measured): S222-S234's even rows, S268-S274, S277-S279, S286, S288, S289. Item 5's: the dither rows and S239 (every effect, dither included); S247 is overlay's. The number text's awk emulation now lives in fmt.py alone (calc, round_int), marked as scaffolding; its replacement is phase 6's.
- [x] dither and datamosh (multi-pass), camcorder. camcorder.py (the stamp's clock -- the file's creation time in local time, that wall clock read as UTC, as bash's two date calls did -- and its ASS text, gawk's under LC_ALL=C: English names fixed), mosh.py (scdet's cuts, the kept keyframes, the heal, bash's 25/1 fallback), effects/filters.py (the camcorder's ass; the effects split around the mosh pass, stage a in it, stage b after; the dither: its chain, the palette pass, paletteuse on 1:v or 2:v; an Effects record for the three things every builder took), and the job's passes in bash's order (the script, the cuts -- read-only, run under --dry-run too -- the mosh pass, the chain, the palette pass, the render). Proven against bash's own functions: cam_prepare's script byte for byte, 300 cases in 3 zones; mosh_prepare's analysis and pass, 216 cases; fx_chain with dither, stages and the camcorder, and fx_palette's command, 24 cases; 13 mutants caught. G1/G2 live: run.sh 289/289, matrix.sh 754/754, 0 differ; same 118 -> 126 and 446 -> 467; no effect unported; the camcorder's script compared by content where its clock was given. Ported (suite/test_multipass.py): the dither's colours and formats, every effect at once, the clock's checks, the stamp drawn, datamosh's frames kept and its melting and healing (their numpy measures computed in Python, on the same frames), the refusals (surface); 24 rows stated. Found on the way: my own oracles' faults, each fixed -- bash's EXIT trap removed the last case's work dir (a subshell a case), an f-string ate bash's braces, fx_palette was given the wrong input; a job test passed for the wrong reason (rewritten); basedpyright misread a raw f-string's \N{name} (the ASS break named instead).
- [x] subtitles: ingest (all formats), bar detection, placement, the ASS renderer. *6a, ingest, done: subs/ingest.py, stage by stage on bash's intermediate text (jq's @tsv escapes and tonumber? -- its grammar probed: ASCII digits, blanks around, nan null, inf the largest double -- gawk's numbers, FPAT's leftmost-longest fields, sort -n's key); equal to bash's ingest_subs on the 21 fixtures and 27 hostile transcripts (tables, words, notes, refusals); invariants of any transcript in the Nix suite. Found: the port crashed on an "inf" time (floor of infinity), and read "1_000" and other scripts' digits, which jq refuses -- both fixed, both tested; bash's gawk counted bytes under C (a correction, CHANGELOG). A transcript's backslash is burned doubled (jq's @tsv escape never undone) -- stage A keeps it; phase 6. 6b, layout, done: subs/layout.py (font_size; bottom_bar's seven cropdetect samples, the log read, the bar used when it holds the text); equal to bash's bottom_bar on 168 cases, the size deciding and the exact threshold among them; 2 mutants caught. 6c, the ASS renderer, done: subs/ass.py (write_ass and its gawk, event for event: the four modes, wrapping, the bar, the two highlight layers); byte-equal to bash's on 3000+ scripts (41 transcripts x modes x sizes x frames x bars x margins) and on 150 generated transcripts (Hypothesis); invariants of any script on 300 more; 6 mutants caught. Found: str.split() is not awk's split (NBSP, U+3000: a transcript now holds both). 6d, burning, done: burn() in jobs/convert.py in cmd_overlay's order (ingest and what the mode needs of it, the head, the camcorder, the bar found on the picture the text will sit on, the script written or one's own copied, FFMAN_FONTS_DIR checked, the passes with the subtitles drawn after the tape's effects, the kind checked after them, as bash); the render shared with resize (_render: bash's two commands end alike); the subtitles part of Effects; the harness runs both sides under C.UTF-8 (dual.py). Live: run.sh 289/289 and matrix.sh 754/754, 0 differ; same 126 -> 153 and 467 -> 639. Found by G1, each fixed with a test that fails on the old code: the bar's -vf graph stripped the wrong input labels on a multi-chain head (built from an unlabelled start now), and the subtitles were drawn in the mosh pass. Ported: suite/test_subtitles.py, 100 rows (265 of 1043); the pixel measures in Python, each shown to tell no text, text and a highlight apart. The transcript fixtures are copied into tests/fixtures/transcripts (the Nix source has no bash suite): phase 5 deletes the originals. Open: S053 (the pop's geometry: phase 4), S124-S126 (A/V sync through a burn), S158-S159 (fuzz.py's invariants -- its own, not the Hypothesis property's yet). 6d, burning, done (08661a9): burn() in cmd_overlay's order; live equal. Open rows, planned: S053 (the pop's geometry, phase 4), S089-S092 (A/V sync through a burn: measures to port), S158-S159 (fuzz.py's invariants -- chunks never overlap, a showable span a word, no line below the frame, no ASS syntax from the text -- into the Hypothesis property, which checks others today).* Hypothesis property: bash and Python ASS text equal on generated transcripts -- done (6c, 150 examples).
- [x] soft subtitles: copy-only planning, languages, in place. *6e: attach() (bash's cmd_attach: the codec by the output's family, an ASS kept styled in Matroska, SRT clipped to the media -- subs/srt.py, equal to bash's write_srt on the fixtures and hostile transcripts at four clips -- across families only what fits, the language at the new track's index). Live: run.sh 162 same, matrix.sh 715 same, 0 differ (M5-M10 and M11 run apart: a sandbox restart cut the whole run). Ported: the attach checks (S070-S083, S156-S157, S110-S111), M6's 84 cases with matrix.sh's oracle (66 codecs checked, 2 refused, 16 rejected by the container itself, as matrix.sh accepted); in place is --in-place now (surface). 370 of 1043 rows.*
- [x] YouTube preset, normalisation. *youtube() (jobs/convert.py): bash's convert in its order on phase 2's planning -- the source's refusals, the output (.mp4 by default), the picture's filters, the sound (absent: a note; AAC LC 48 kHz stereo: copied; else ffmpeg-normalize, run as bash ran it, env XDG_CONFIG_HOME=... and its preset checked), x264's two passes. Live: equal. Ported (suite/test_youtube.py; check.py's youtube() whole -- the probe, x264's own record of its options, the MP4 box tree): S084-S088, S112-S126, and the A/V sync through a burn, S089-S092 (tests/support/measures.py: check.py's sync, sub_sync and red, equal to check.py's on the same files). Mutants: 3 of 4 caught; the fourth, +cgop dropped, is equivalent -- x264's GOP is closed by default (its record says open_gop=0 either way); tests/test_encode.py pins the flag. 394 of 1043 rows; the stage-A refusal "not ported yet" has no caller left (removed; the harness keeps its own copy to classify). The sound is three types now -- Silent(note), Copied(), Normalised(preset, note) -- so no outcome can lack what it says or uses (the optional fields and their guards were unreachable branches); a fourth kind would not type-check where the job reads it.*
- [x] G1 and G2 on the whole corpus, as an explicit derivation: `nix build .#ffman-equivalence` (not part of `nix flake check`: the runs are long, both implementations render). *Done: the owner's build at 56cd41a is clean -- in the Nix sandbox, with the pin's tools, every invocation of both suites the same (run.sh 168, matrix.sh 737; nothing unported); the 12 that leave the camcorder's clock to the run compared by their commands (G1). The way there found four faults, each fixed with a test that fails on the old code: a stale shim directory reused, the harness's scratch following a case's TMPDIR, ffman reading installed metadata at import, run.sh's S207 shim needing /usr/bin/env. "G3 green" moved to phase 4's first item: it needs every port.*

**Phase 4: tests complete**
- [x] All 289 + 754 + properties in pytest, passing (G3 green); `LEDGER.md` fully mapped (G5). *Done: every one of the 1043 rows stated -- 993 mapped, 50 surface (a spelling or a message the new CLI renamed: its new form tested, the old one naming it), none changed; every target a test in tests/suite or the unit tests (none in tests/equivalence, which phase 5 deletes). Passing on the Nix source set: the suite 785 at 100% line and branch; the matrix, ffman-next-matrix (pytest -m slow -n auto), 761. Each section ported with matrix.sh's or run.sh's own oracle and checked: ids against the ledger's titles, numpy measures against run.sh's and check.py's formulas on the same files (to 4 decimals), mutants caught by exactly the rows they touch. Porting found and fixed two harness adaptations that changed an invocation's meaning (an = form split, a dangling value option), a measure reading 16-bit frames as 8-bit, and text_band comparing other frames than check.py's.*
- [x] Coverage ≥ 95%, vulture clean, basedpyright and ruff clean; ty advisory run recorded. *Done: coverage 100% line and branch on the suite (785), with no exclusion anywhere (no `pragma: no cover`, no omit); ruff and basedpyright (all, against the pin's test interpreter) clean, the matrix 761 passing. vulture (2.14, the pin's) found eight in the product, each settled: five dead (`Labels.reserve`, `ass.MODES` -- a second, reordered copy of OVERLAY_MODES -- `Sound.action`, derivable from its codec, `highlight_mode_given`, `Addition.existing_subtitles`); two rules held twice, the tested copy unused (`plan.addition`/`subtitle_codec` beside attach()'s inline table and branches, `check_burn_source` beside burn()'s check) -- one copy each now, attach() calling bash's shape (`attach_streams`), its commands unchanged live (run.sh 168, M6 84 the same); and `-v/--verbose`, accepted and ignored -- out until stage B gives it a meaning (ffman-spec §1). vulture now runs in ffman-next-lint, scoped by `[tool.vulture]`. ty (0.0.38, the pin's) advisory, with the pin's test interpreter (`--python`): clean on all 102 files -- without it, ty resolves another Python and reports 66 unresolved imports.*

**Phase 5: switch and retire bash** (the equivalence gates would fail by design once stage B starts)
- [x] The `ffman` package becomes the Python one; `ffman-next` and its checks are renamed. *Done: `ffman` is the Python package, its checks `ffman-tests`, `ffman-matrix`, `ffman-lint`, `ffman-types`; the bash package is gone (nothing used it -- its suite and the comparison run the raw script), its suite `ffman-bash-tests` until the next item. Evaluated: the package, its suite and matrix, the dev shell and ffman-equivalence the same derivations as before; lint, types and the bash suite the same but for their names (compared field by field). The host installs ffman-2.0.0.dev0 where it installed the bash ffman, wrapped on the system's ffmpeg-full (FDK), the flake's on the stock one. Every command the Python ffman runs is in its wrapper's PATH (ffmanRuntime). New, `ffman-installed`: the built binary run as a user runs it (env -i: its wrapper alone gives PATH and environment), one job per runtime tool -- the suite calls main() in-process and could not see the wrapper; rehearsed here with a stand-in wrapper, every job ran.*
- [x] Delete `tools/ffman.sh`, `tools/ffman-tests/`, `ffmanTools`' bash-only tools, the equivalence harness, the adapter and `tools/ffman/migration/` (corpus, ledger, generator). *Done: 53 files removed (git history keeps them); with them ffmanTools, ffmanSuitePython, ffman-bash-tests, ffman-equivalence, the `equivalence` marker and its lint ignores. Checked before: nothing that stays read or imported them (three comments did); the test-support modules all stay in use. ffman-matrix now sets `disabledTestMarks = [ ]` -- left out, it inherits the suite's `[ "slow" ]`, and "((slow)) and not (slow)" runs nothing, silently; evaluated: the suite `-m "not (slow)"`, the matrix `-m "((slow))"`. Comments and docstrings that pointed at what went now speak of it as stage A's (the ids: the bash checks they port, as the ledger numbered them). The suite 785 at 100% (the 761 deselected exactly the matrix), the matrix 761, ruff, basedpyright, vulture and ty clean; the flake evaluates, the host installs ffman-2.0.0.dev0, no code names a deleted path. The docs that do are item 3's.*
- [x] Docs: `07-tools.md` rows name modules; run-book items updated; `AGENTS.md` routing line. *Done: 07-tools.md's ffman section describes the Python ffman and its five checks; its 42 decision rows gained a Where column, each module found in the code by the row's own tokens, not its title; retired flags and commands renamed (`--vfx`, `--add-subs`, the camcorder's `date=`/`time=`, checked against the code); a row with a stray `|` (always one cell too many) fixed. Run-book 11.49: builds the checks, drops jq (ffman has none), names modules, and corrects "steps=3" (the blur and the bar blur use 6, halation and VHS 3). AGENTS.md routes tools/ffman/ to its own AGENTS.md. New, at the owner's request: tools/ffman/README.md (every example run through --dry-run) and AGENTS.md (layout, checks, rules -- each as configured or stated). D5 records the build backend, and bytecode's place. The review maps rescanned: the doc map places tools/ffman/ (concept) and resolves a document's own-directory paths (locate()), its selftest passing; the Nix map's changes only recomputed facts, review state kept.*
- [x] G6: grep, vulture, coverage; `nix flake check` green. *Done: the owner's `nix flake check` is clean (aarch64-linux omitted by design: no builder for it). Shown here: the Appendix's 86 functions each found in the code or dropped with a reason; the grep's hits all history (104 in tests, every one a comment or docstring, parsed) or other tools' scripts; vulture 0; coverage 100%, no exclusion; ruff's TD/FIX/ERA active (a probe file raised all three) and clean; the docs name modules (one `optimize_output` left, now `encode.optimizer`).*

**Phase 6: stage B, intended changes** -- its own plan, [`ffman-phase6.md`](ffman-phase6.md): the findings of an assessment at its start (awk's arithmetic and what compensated for it, bash's ways written in Python, architecture, DRY), the effects researched before they change (a `vfx-<effect>` skill each), and its checklist. Every item listed here before is carried there; fuzz.py's invariants, listed here too, were done in phase 4.

**Phase 7: new capabilities**
- [ ] `concat` (stream compatibility: refuse, or conform to the first input).
- [ ] `transcribe` (whisper.cpp; the model path passed explicitly).
- [ ] Audio effects (`--afx`), through the same registry and planner.
- [ ] Optionally, `--look` presets spanning video and audio.
- [ ] `probe`.

## Appendix: function ledger (bash → Python)

Every function of the last bash ffman (86, from git at 800537c), where it lives
now -- each checked in the code at phase 5 (G6) -- or why it is gone.

| Bash functions | Python |
|---|---|
| `die note cleanup on_signal run workdir run_ffmpeg ffargs` | `errors.py` (`refuse`); `run.py` (`note`; `Runner`: `run`, `workdir`, the cleanup on exit, `ffmpeg`; `_on_signal`; `ffmpeg_args`) |
| `take optval parse_shared usage usage_convert fx_help main` | `options.py` (`parse`, its value taking; `format_help`); `effects/__init__.py` (`format_catalogue`: `ffman effects`); `cli.py` (`main`) |
| `validate_shared` | `jobs/convert_options.py` (`validate`) |
| `cmd_resize cmd_overlay cmd_attach cmd_convert` | `jobs/convert.py`: `resize`, `burn`, `attach`, `youtube` -- one command, `convert` |
| `lower`, `usage_resize usage_overlay usage_attach`, `src` | dropped: `str.lower`; the three commands are `convert`'s options now (their old spellings refused, naming the new); the `file:` URL is an f-string where an input is named (`probe.py`, `jobs/convert.py`, `subs/layout.py`) |
| `ext_of same_file resolve_output finish` | `output.py` |
| `is_image_ext`, `is_uint is_num` | `plan.py` (`is_image`); `checks.py` |
| `calc round_int` | `fmt.py` (stage A's number text; phase 6 makes it exact) |
| `round_even plan_dimensions geometry` | `geometry.py` (`round_even`, `target_size`, `displayed`) |
| `probe pq` | `probe.py` |
| `resize_filter bblur_sigma`, `bblur_on` | `resize.py`; `jobs/convert_options.py` |
| `family container_flags ffv1_slices src_tb optimize_output` | `encode.py` |
| `video_encoder audio_encoder image_encoder gif_encoder` | `plan.py` (which encoder, the refusals), `encode.py` (its settings) |
| `carry_tracks loop_check yt_bitrate fps_of`, `cmd_convert`'s decisions | `plan.py` (`tracks`, `check_loop`, `youtube_kbps`, `fps_of`, `youtube_video`, `youtube_sound`) |
| `have_encoder`, `gif_chain` | `jobs/convert.py` (`encoders`: `ffmpeg -encoders` once); `gif.py` |
| `light_luts` | `light.py` |
| `fx_set fx_validate`, `fx_any fx_pre fx_post fx_chain fx_palette` | `effects/__init__.py` (the registry, `parse_specs`); `effects/filters.py` (the passes run in `jobs/convert.py`) |
| `vhs_chain vhs_noise vhs_noise_filters crt_chain`, `cam_prepare`, `mosh_prepare` | `effects/filters.py`; `camcorder.py`; `mosh.py` |
| `ingest_subs subs_json_whisper_cli subs_json_segments subs_srt_vtt is_highlighted subs_highlighted subs_lrc subs_table normalize_cues normalize_words` | `subs/ingest.py` (`ingest`, `_whisper_cli`, `_whisperx`, `_srt_vtt`, `_is_highlighted`, `_highlighted`, `_lrc`, `_table`, `_normalize_cues`, `_normalize_words`) |
| `font_size bottom_bar`, `write_ass`, `write_srt`, `sub_codec_for` | `subs/layout.py` (`font_size`, `bar_*`); `subs/ass.py` (`script`); `subs/srt.py`; `plan.py` (`subtitle_codec`, `attach_streams`) |
