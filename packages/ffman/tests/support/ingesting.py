"""A transcript file ingested as the job ingests one: its bytes read (read_file), then ingest."""

from pathlib import Path

from subverter.transcript import Transcript

from ffman.media.paths import read_file
from ffman.subs.ingest import ingest


def ingested(path: str | Path) -> Transcript:
    """``path``'s transcript, read as the job reads it -- "no such file" included."""
    return ingest(str(path), read_file(str(path)))
