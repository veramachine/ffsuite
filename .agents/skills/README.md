# Skills

ffman's agent skills, one directory each: `<name>/SKILL.md` and what it
references (`references/`, `scripts/`). Every skill about ffman or the formats
it reads and writes lives here, not in nixos-config (the owner's decision).

- **Format**: skill-creator's. The frontmatter holds `name` (kebab-case, at most
  64 characters) and `description` (at most 1024, no angle brackets), and no key
  but its allowed ones. Its `quick_validate.py` checks a skill; its
  `package_skill.py` makes `<name>.skill`, the zip Claude installs. Both ship
  with skill-creator in Claude's skills, not here.
- **Sources**: every figure cited, every measurement a script in `scripts/`, run.
  Phase 6's effect skills (`vfx-<effect>`) follow
  [`ffman-phase6.md`](../../docs/ffman-phase6.md) §4.
- **Oracles**: `cue`, `ffmetadata` and `vorbiscomment` are ffmeta's tests'
  references too -- its tests (`packages/ffmeta/tests/`) hold the code to each
  `SKILL.md`'s own text, and `test_skills.py` its examples, word for word: a
  change to a skill is a change to a test.
