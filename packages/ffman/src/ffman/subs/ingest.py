"""Transcripts in, chunks and words out: the bash ffman's ingest_subs, stage by stage.

The format's reader (``readers``) gives cues; the normalisers (``normalize``)
make them chunks and, where the source times words, words. ASS and SSA pass
through: burned as they are.
"""

from subverter import readers
from subverter.transcript import Transcript

from ffman.errors import refuse
from ffman.media.paths import ext_of
from ffman.subs import normalize


def ingest(name: str, data: bytes) -> Transcript:
    """A transcript from its bytes, as bash's ingest_subs read it: its refusals, its notes."""
    fmt = ext_of(name)
    if fmt in ("ass", "ssa"):  # burned as they are
        return Transcript(fmt, f".{fmt}", has_words=False, chunks=(), words=(), notes=())
    found = readers.read(fmt, data, name)
    chunks = normalize.cues(found.cues, references=found.has_references)
    if not chunks:
        refuse(f"no timed text found in: {name}")
    notes = list(found.notes)
    if not found.has_words:
        return Transcript(fmt, found.source, found.has_words, chunks, (), tuple(notes))
    placed_words, placed, untimed = normalize.words(
        chunks, found.words, references=found.has_references
    )
    if placed:
        why = "(untimed, tied, out of order or outside their sentence)"
        notes.append(
            f"{placed} words had no usable time of their own {why}: placed between their neighbours"
        )
    if untimed:
        notes.append(f"{untimed} sentences had no word timings: shown without word highlighting")
    return Transcript(fmt, found.source, found.has_words, chunks, placed_words, tuple(notes))
