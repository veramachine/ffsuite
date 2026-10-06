"""Subtitle and transcript readers into one model: cues, word timings, notes, refusals.

SubRip, WebVTT, LRC, CSV and TSV, and whisper-cli's and WhisperX's JSON (``readers.FORMATS``).
"""

from subverter._errors import Error
from subverter.markup import untagged
from subverter.readers import FORMATS, read
from subverter.transcript import Chunk, Cue, Reading, Timing, Transcript, Word

__all__ = [
    "FORMATS",
    "Chunk",
    "Cue",
    "Error",
    "Reading",
    "Timing",
    "Transcript",
    "Word",
    "read",
    "untagged",
]

Error.__module__ = "subverter"  # tracebacks name the public subverter.Error, not its private module
