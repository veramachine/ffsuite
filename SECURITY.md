# Security Policy

## Supported Versions

Security updates are applied to the latest `main` branch and to each package's
most recent release: its latest tag (`ffman-v*`, `ffmeta-v*`, `subverter-v*`)
and that version on PyPI.

## Reporting a Vulnerability

**Do not open a public issue for security vulnerabilities.** To report one, use
the [Private Vulnerability Reporting](https://github.com/veramachine/ffsuite/security/advisories/new)
feature in this repository.

Please include the technical context needed to reproduce it:

- The package (ffman, ffmeta or subverter) and the version or commit affected.
- The exact input, command line, or API call.
- Host OS, Python version, and ffmpeg version (`ffmpeg -version`) when ffman
  runs it.
- Exact reproduction steps or a proof-of-concept.

You can expect an initial response within a few days. Please give us a
reasonable window to ship a fix before disclosing publicly.
