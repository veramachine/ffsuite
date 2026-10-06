"""subverter's tests: Hypothesis reproducible."""

from hypothesis import settings

# Reproducible everywhere, the Nix sandbox included: the same examples each run, no database.
settings.register_profile("subverter", derandomize=True, database=None)
settings.load_profile("subverter")
