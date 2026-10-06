"""subverter's README: its examples run as written, their output as shown (doctest).

Only what the ``pycon`` fences hold is run -- the fences themselves are not an example's output,
however the Markdown around them is formatted (dprint drops the blank line doctest would need).
"""

import doctest
import re
from pathlib import Path
from typing import Final, cast

README: Final = Path(__file__).resolve().parents[1] / "README.md"
_FENCED: Final = re.compile(r"^```pycon\n(.*?)^```$", re.MULTILINE | re.DOTALL)


def test_the_readmes_examples_run_as_written() -> None:
    # one group: findall gives each block's text
    blocks = cast("list[str]", _FENCED.findall(README.read_text(encoding="utf-8")))
    assert blocks  # a README without its examples passes nothing
    runner = doctest.DocTestRunner()
    for number, block in enumerate(blocks, start=1):
        test = doctest.DocTestParser().get_doctest(block, {}, f"README #{number}", str(README), 0)
        _ = runner.run(test)
    assert (runner.failures, runner.tries > 0) == (0, True)
