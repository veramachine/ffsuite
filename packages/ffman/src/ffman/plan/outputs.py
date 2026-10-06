"""What a job writes: the output's kind, its refusals, an image's encoder.

Small pure functions returning data, called by the job in its bash command's
own order (overlay resolved its output late, resize early).
"""

from dataclasses import dataclass
from enum import Enum, auto

from ffman.errors import refuse
from ffman.plan.encode import IMAGE_ENCODERS, IMAGE_INPUTS
from ffman.plan.request import ConvertOptions


class Output(Enum):
    """What the output holds, by its extension."""

    VIDEO = auto()
    IMAGE = auto()
    GIF = auto()


@dataclass(frozen=True, slots=True)
class ImageFrame:
    """One frame, as an image."""

    ext: str
    encoder: str


def is_image(ext: str) -> bool:
    """An extension bash read as a still picture (``is_image_ext``)."""
    return ext in IMAGE_INPUTS


def check_burn_source(in_ext: str, path: str) -> None:
    """Burning needs a video (bash's overlay, right after probing)."""
    if is_image(in_ext):
        refuse(f"overlay needs a video, not an image: {path}")


def output_kind(o: ConvertOptions, *, burn: bool, moving: bool, out_ext: str) -> Output:
    """What the output is; bash's refusals of a kind it could not make, and the loop rules."""
    kind = Output.GIF if out_ext == "gif" else Output.IMAGE if is_image(out_ext) else Output.VIDEO
    if o.metadata is not None:
        check_tags(out_ext)
    if burn:
        if kind is Output.IMAGE:
            refuse("overlay output must be a video")
    elif moving and kind is Output.IMAGE:
        refuse(f"a video cannot be resized into an image (.{out_ext})")
    elif not moving and kind is Output.VIDEO:
        refuse(f"an image cannot be resized into a video (.{out_ext})")
    check_loop(o, kind, moving=moving)
    return kind


def check_tags(ext: str) -> None:
    """--metadata wants an output that holds tags and chapters: not a GIF, not an image."""
    if ext == "gif" or is_image(ext):
        refuse(f"--metadata: a .{ext} holds no tags or chapters")


def check_loop(o: ConvertOptions, kind: Output, *, moving: bool) -> None:
    """--loop and --loop-reverse describe a GIF that moves (bash's loop_check)."""
    if o.loop == "once":
        return
    if kind is not Output.GIF:
        refuse("--loop and --loop-reverse need a .gif output")
    if not moving:
        refuse("--loop and --loop-reverse need a moving source: an image makes a one-frame GIF")


def check_moving(o: ConvertOptions, *, moving: bool) -> None:
    """Datamosh melts scene cuts: a still image has none (bash's resize)."""
    if not moving and any(r.effect.name == "datamosh" for r in o.effects):
        refuse("--datamosh melts scene cuts: it needs a moving source")


def image_frame(out_ext: str) -> ImageFrame:
    """One frame, in its format's encoder (bash's image_encoder: bmp is read, never written)."""
    encoder = IMAGE_ENCODERS.get(out_ext)
    if encoder is None:
        refuse(f"unsupported image output '.{out_ext}' (png, jpg, webp, avif, tiff)")
    return ImageFrame(out_ext, encoder)
