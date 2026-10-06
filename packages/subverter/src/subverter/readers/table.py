"""CSV and TSV, as whisper-cli and WhisperX write them: start, end, text (ms), columns by header.

A header is a first record naming start and end, in any order (bash: one starting with
start); without one, the columns are start, end, text.
"""

import csv
import io

from subverter.readers.fields import time_ms
from subverter.transcript import Cue

__all__ = ["rows"]


def rows(kind: str, text: str) -> list[Cue]:
    """whisper-cli .csv (RFC 4180 quoting) or WhisperX .tsv (tabs, none); a time read, or none."""
    lines = io.StringIO(text, newline="")
    records = (
        csv.reader(lines, delimiter="\t", quoting=csv.QUOTE_NONE)
        if kind == "tsv"
        else csv.reader(lines)
    )
    si, ei, ti = 1, 2, 3
    found: list[Cue] = []
    for n, fields in enumerate(records):
        names = [f.lower() for f in fields] if n == 0 else []
        if "start" in names and "end" in names:  # a header: its columns, any order (the last named)
            for i, name in enumerate(names, 1):
                si = i if name == "start" else si
                ei = i if name == "end" else ei
                ti = i if name == "text" else ti
            continue
        if fields and len(fields) >= ti:
            found.append(
                Cue(time_ms(fields[si - 1], 1), time_ms(fields[ei - 1], 1), fields[ti - 1])
            )
    return found
