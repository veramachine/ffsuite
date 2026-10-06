import math

import pytest

from ffman.fmt import awk_print

# Each pair confirmed against GNU Awk 5.2.1's `print` (docs/ffman-python.md: stage A).
GAWK = [
    (1.5, "1.5"),
    (0.05, "0.05"),
    (0.005, "0.005"),
    (1 / 3, "0.333333"),
    (0.05573, "0.05573"),
    (57 / 38 * 1.65, "2.475"),
    (123456.7, "123457"),
    (1234567.8, "1.23457e+06"),
    (1e-7, "1e-07"),
    (-1.5, "-1.5"),
    (0.0, "0"),
    (2.0, "2"),
    (-2.0, "-2"),
    (12345678.0, "12345678"),
    (2.0**53, "9007199254740992"),
    (2.0**100, "1267650600228229401496703205376"),
    (9223372036854775807.0, "9223372036854775808"),
]


@pytest.mark.parametrize(("x", "printed"), GAWK)
def test_awk_print_matches_gawk(x: float, printed: str) -> None:
    assert awk_print(x) == printed


@pytest.mark.parametrize(
    ("x", "gawk"),
    [(math.inf, "+inf"), (-math.inf, "-inf"), (math.nan, "+nan"), (-math.nan, "-nan"), (-0.0, "0")],
)
def test_non_finite_as_gawk(x: float, gawk: str) -> None:
    # gawk 5: print 1e400, -1e400, -log(-1), log(-1), -0 (probed)
    assert awk_print(x) == gawk
