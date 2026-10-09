"""A transcript, as ffman reads one: its chunks and words, and what its readers found."""

from dataclasses import dataclass

__all__ = ["Chunk", "Cue", "Reading", "Timing", "Transcript", "Word"]


@dataclass(frozen=True, slots=True)
class Chunk:
    """A timed piece of text, its times in milliseconds (bash's chunks.tsv)."""

    start: int
    end: int
    text: str
    segment: str


@dataclass(frozen=True, slots=True)
class Word:
    """A timed word of a chunk, its times in milliseconds (bash's words.tsv)."""

    segment: str
    start: int
    end: int
    text: str


@dataclass(frozen=True, slots=True)
class Transcript:
    """What ingesting found: the format, its source's name, the chunks, the words, the notes."""

    fmt: str  # bash's SUBFMT: the extension
    source: str  # bash's SUBSRC: the source's name, in messages
    has_words: bool  # bash's HAS_WORDS: the source times words
    chunks: tuple[Chunk, ...]
    words: tuple[Word, ...]
    notes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Cue:
    """A timed text as its reader found it: whole ms (None: no time read), its markup kept."""

    start: int | None
    end: int | None
    text: str
    segment: str = ""  # the sentence its words name, where words are timed


@dataclass(frozen=True, slots=True)
class Timing:
    """A word as its reader found it: its sentence, whole ms (None: no time read), its text."""

    segment: str
    start: int | None
    end: int | None
    text: str


@dataclass(frozen=True, slots=True)
class Reading:
    """A reader's answer: its source's name, word timings or not, its cues, words and notes.

    ``has_references``: its texts are WebVTT's, where ``&`` begins an HTML character
    reference (W3C WebVTT, the cue text tokenizer: "HTML character reference in data
    state") -- each run between tags decoded (``decoded``), so a decoded ``<`` stays text. A
    highlighted reading's sentences come untagged: WhisperX's tags wrap whole words.
    """

    source: str
    has_words: bool
    cues: tuple[Cue, ...]
    words: tuple[Timing, ...] = ()
    notes: tuple[str, ...] = ()
    has_references: bool = False
