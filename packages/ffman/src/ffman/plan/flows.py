"""Which job a convert command is: its flow, from its options alone (spec 3.8).

What a bash command did -- resize, overlay, attach or convert (YouTube) -- is
chosen here; what no bash command did is refused, for now.
"""

from enum import Enum, auto

from ffmeta.files import TEXT_PRESETS, check_output, is_metadata

from ffman.errors import refuse
from ffman.media.paths import ext_of
from ffman.plan.request import ConvertOptions


class Flow(Enum):
    """Which bash command a job does; or a metadata file's job (New, spec 3.9)."""

    METADATA = auto()  # a metadata file in or out
    PICTURE = auto()  # resize; overlay with --burn-subs
    TRACKS = auto()  # attach
    REMUX = auto()  # another container, a codec, --metadata: the rest copied (New, spec 3.11)
    YOUTUBE = auto()  # convert --preset youtube


def _picture_options(o: ConvertOptions) -> list[str]:
    """The options only the picture flow reads (its GIF's loop too), as named to the user."""
    given = [
        ("-w", o.width is not None),
        ("-H", o.height is not None),
        ("-a", o.aspect is not None),
        ("-b", o.bblur_on),
        ("-r", o.resize_mode != "fit"),
        ("--vfx", bool(o.effects)),
        ("--burn-subs", o.burn_subs is not None),
        ("--loop", o.loop == "loop"),
        ("--loop-reverse", o.loop == "reverse"),
    ]
    return [name for name, on in given if on]


def _codec_options(o: ConvertOptions) -> list[str]:
    given = [
        ("--video-codec", o.video_codec is not None),
        ("--audio-codec", o.audio_codec != "copy"),
        ("--lossless", o.lossless),
    ]
    return [name for name, on in given if on]


def _metadata_only(o: ConvertOptions, output_ext: str, others: list[str]) -> None:
    """A metadata job: its output a metadata file, no other option, a preset a .txt's alone."""
    if not is_metadata(output_ext):
        refuse(f"a metadata file makes a metadata file: {o.output}")
    given = [
        *others,
        *(["--add-subs"] if o.add_subs else []),
        *(["--preset youtube"] if o.preset == "youtube" else []),
    ]
    if given:
        refuse(f"a metadata file is a job of its own: {given[0]} cannot be added")
    check_output(output_ext, o.preset if o.preset != "youtube" else None)


def select_flow(o: ConvertOptions) -> Flow:
    """The job's flow, from its options alone (before the file is probed)."""
    picture = _picture_options(o)
    # the default output, and --in-place's, keep the input's extension
    output_ext = ext_of(o.input if o.in_place or o.output is None else o.output)
    if is_metadata(ext_of(o.input)) or is_metadata(output_ext):
        tagged = ["--metadata"] if o.metadata is not None else []
        _metadata_only(o, output_ext, [*picture, *_codec_options(o), *tagged])
        return Flow.METADATA
    if o.preset in TEXT_PRESETS:
        refuse(f"--preset {o.preset} is for a .txt output")
    if o.preset is not None:
        extra = [*picture, *(["--add-subs"] if o.add_subs else [])]
        if extra:
            refuse(f"--preset youtube is a job of its own: {extra[0]} cannot be added, for now")
        return Flow.YOUTUBE
    if o.add_subs:
        extra = [*picture, *_codec_options(o)]
        if extra:
            refuse(
                f"--add-subs copies the picture and the sound: {extra[0]} cannot be added, for now"
            )
        return Flow.TRACKS
    sized = o.width is not None or o.height is not None or o.aspect is not None
    if o.burn_subs is not None and not sized and (o.bblur_on or o.resize_mode != "fit"):
        refuse("--bblur and --resize-mode need a size or a ratio to resize to (-w, -H or -a)")
    if not (sized or o.effects or o.burn_subs is not None):
        if output_ext != ext_of(o.input) or _codec_options(o) or o.metadata is not None:
            return Flow.REMUX
        asks = "a size (-w, -H, -a), an effect (--vfx), subtitles (--burn-subs, --add-subs)"
        refuse(f"convert: nothing to do: give {asks}, another container, a codec or --preset")
    return Flow.PICTURE
