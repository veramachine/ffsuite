"""A metadata file's format, by its name and first line, and the presets each output takes.

The spec's rules: a metadata file is a .ffmeta, a .txt (ffmetadata or Vorbis comments, told by
its first line) or a .cue (3.13); a .ffmeta or .cue output takes no preset -- ``--preset P: a .EXT
output is FORMAT`` -- and a cue sheet no .txt (``--preset cue: a .txt output is ...``).
"""

from fractions import Fraction

import ffmeta
import pytest
from ffmeta import files
from ffmeta._errors import refuse_at


@pytest.mark.parametrize(
    ("ext", "held"), [("ffmeta", True), ("txt", True), ("cue", True), ("mkv", False), ("", False)]
)
def test_a_metadata_file_by_its_extension(ext: str, held: bool) -> None:
    assert files.is_metadata(ext) is held


@pytest.mark.parametrize(
    ("ext", "text", "fmt"),
    [
        ("ffmeta", "TITLE=x\n", "ffmetadata"),  # by its extension, whatever it holds
        ("cue", ";FFMETADATA1\n", "cue"),
        ("txt", ";FFMETADATA1\ntitle=x\n", "ffmetadata"),  # a .txt by its first line
        ("txt", "TITLE=x\n", "vorbis"),
    ],
)
def test_a_file_read_its_format(ext: str, text: str, fmt: str) -> None:
    assert files.format_in(ext, text) == fmt


@pytest.mark.parametrize(
    ("ext", "preset", "fmt"),
    [
        ("ffmeta", None, "ffmetadata"),
        ("cue", None, "cue"),
        ("txt", None, "ffmetadata"),  # a .txt by its preset, ffmetadata without one
        ("txt", "vorbiscomment", "vorbis"),
        ("txt", "ffmetadata", "ffmetadata"),
    ],
)
def test_a_file_written_its_format(ext: str, preset: files.Preset | None, fmt: str) -> None:
    assert files.format_out(ext, preset) == fmt


@pytest.mark.parametrize(
    ("preset", "fmt"), [("ffmetadata", "ffmetadata"), ("vorbiscomment", "vorbis"), ("cue", "cue")]
)
def test_a_preset_names_its_format(preset: files.Preset, fmt: str) -> None:
    assert files.format_of(preset) == fmt


@pytest.mark.parametrize(
    ("ext", "preset", "message"),
    [
        ("ffmeta", "vorbiscomment", "--preset vorbiscomment: a .ffmeta output is ffmetadata"),
        ("cue", "ffmetadata", "--preset ffmetadata: a .cue output is a cue sheet"),
        ("txt", "cue", "--preset cue: a .txt output is ffmetadata or Vorbis comments"),
    ],
)
def test_a_preset_an_output_takes_not_is_refused(
    ext: str, preset: files.Preset, message: str
) -> None:
    with pytest.raises(ffmeta.Error, match=f"^{message}$"):
        files.check_output(ext, preset)


@pytest.mark.parametrize(
    ("ext", "preset"), [("txt", None), ("txt", "vorbiscomment"), ("cue", None), ("ffmeta", None)]
)
def test_an_output_and_its_preset_agree(ext: str, preset: files.Preset | None) -> None:
    files.check_output(ext, preset)  # refuses nothing


def test_write_dispatches_by_format() -> None:
    meta = ffmeta.Metadata(
        tags=(ffmeta.Tag("title", "A"),), chapters=(ffmeta.Chapter(Fraction(0), Fraction(60), ()),)
    )
    assert files.write(meta, "vorbis").text.startswith("title=A\n")
    assert files.write(meta, "ffmetadata").text.startswith(";FFMETADATA1\n")


def test_a_line_before_the_first_is_a_callers_mistake() -> None:
    # lines count from 1 (the GNU form, SOURCE:LINE:): 0 is no line, not a refusal
    with pytest.raises(ValueError, match=r"^lines count from 1, not 0$"):
        refuse_at("a.cue", 0, "x")
