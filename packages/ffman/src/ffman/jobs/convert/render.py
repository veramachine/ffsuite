"""The render: the picture's graph, the streams kept, the output's encoding."""

from dataclasses import dataclass
from pathlib import Path
from typing import Final

from ffman.effects.stages import Effects
from ffman.graph import Open
from ffman.graph.gif import gif_tail
from ffman.jobs.convert import covers, output, subtitles, tagging
from ffman.media.paths import ext_of, file_url
from ffman.media.probe import Media, Video
from ffman.media.run import Runner, note
from ffman.plan.encode import (
    attachment_args,
    audio_args,
    container_flags,
    ffv1_slices,
    gif_args,
    image_args,
    lossless_args,
)
from ffman.plan.outputs import ImageFrame, Output, image_frame
from ffman.plan.request import ConvertOptions
from ffman.plan.streams import (
    Attachments,
    Lossless,
    Sound,
    attachments,
    kept_metadata,
    lossless,
    sound,
)

ONE_FRAME: Final = ("-frames:v", "1", "-update", "1")  # one picture, written over each time


@dataclass(frozen=True, slots=True)
class Passes:
    """What the effects' own passes give the render: its inputs, its picture, its output options."""

    inputs: list[str]  # after the source: the mosh pass's file, the palette
    graph: Open
    output: list[str]  # after the mosh: a constant frame rate


@dataclass(frozen=True, slots=True)
class GifEncoding:
    """A GIF: its frames alone, no other stream (bash's gif_encoder)."""


@dataclass(frozen=True, slots=True)
class ImageEncoding:
    """One picture, by its format's encoder (bash's image_encoder)."""

    image: ImageFrame


@dataclass(frozen=True, slots=True)
class VideoEncoding:
    """The picture losslessly, the sound, the subtitles kept, the attachments carried."""

    picture: Lossless
    audio: Sound
    subtitles: output.Kept
    attached: Attachments
    streams: tuple[str, ...]  # the picture's and the sound's, as the trial held them


type Encoding = GifEncoding | ImageEncoding | VideoEncoding


def encoding(
    o: ConvertOptions, runner: Runner, media: Media, kind: Output, out_ext: str
) -> Encoding:
    """How the render encodes ``kind``: decided -- and refused -- before any work."""
    if kind is Output.GIF:
        return GifEncoding()
    if kind is Output.IMAGE:
        return ImageEncoding(image_frame(out_ext))
    found = output.encoders(runner)
    picture = lossless(o, media, found)
    audio = sound(o, media, found)
    kept_subtitles = subtitles.kept(runner, media, file_url(o.input), out_ext)
    attached = attachments(media, ext_of(o.input), out_ext)
    held = (  # the encoder into the container: asked of ffmpeg before any pass (spec 3.11)
        output.Held(
            "video",
            output.lossless_picture(runner, media, picture.codec),
            picture.codec,
            o.video_codec is not None,
        ),
        output.Held(
            "audio",
            ["-map", "0:a?", *audio_args(audio.codec, audio.encoder, audio.channels or 2)],
            output.named(o.audio_codec, media.audio),
            o.audio_codec != "copy",
        ),
    )
    inputs = ["-i", file_url(o.input)]
    output.check_held(runner, out_ext, inputs, held, container_flags(out_ext))
    streams = tuple(arg for kind in held for arg in kind.args)  # held: the tags' trial's too
    return VideoEncoding(picture, audio, kept_subtitles, attached, streams)


@dataclass(frozen=True, slots=True)
class Render:
    """What the last pass needs: where, its encoding, the source's streams, the picture's graph."""

    target: Path
    encoding: Encoding
    media: Media
    video: Video
    fx: Effects
    passes: Passes
    applied: tagging.Applied  # --metadata's or an attached one (3.10, 3.14)


def run(o: ConvertOptions, runner: Runner, r: Render) -> None:
    """The last pass, as bash's resize and overlay both ended: GIF, image, or the video."""
    inputs = ["-i", file_url(o.input), *r.passes.inputs]
    extra, kept = kept_metadata(inputs, r.applied.path)  # a GIF, an image: refused one (spec 3.10)
    match r.encoding:
        case GifEncoding():
            frames = gif_tail(r.passes.graph, o.loop, r.fx.labels)
            args = [*_filtered(inputs, frames), *gif_args(o.loop), *r.passes.output]
        case ImageEncoding(image):
            one = [*ONE_FRAME, *image_args(image.encoder)]
            args = [*_filtered(inputs, r.passes.graph), *one]
        case _:  # the union's last, a VideoEncoding: the checker narrows it, nothing falls through
            picture, audio = r.encoding.picture, r.encoding.audio
            told, attached = r.encoding.subtitles, r.encoding.attached
            source = ["-i", file_url(o.input)]
            flags = container_flags(ext_of(str(r.target)))
            whole = [*source, *extra, *r.encoding.streams, *kept, *flags]
            given = tagging.Given(r.media, o.input, r.applied.path)
            tagged = tagging.tagging(runner, given, whole, ext_of(str(r.target)))
            carried_t = len(r.media.attachments) if attached.carry else 0
            job = covers.Job(
                file_url(o.input), tuple(whole), 1, carried_t
            )  # one picture: the graph's
            cover = covers.kept(runner, r.media, ext_of(str(r.target)), job)
            for line in (
                *r.applied.notes,
                *told.notes,
                *cover.notes,
                *([attached.note] if attached.note else []),
                *tagged.notes,
            ):
                note(line)
            # the effects' frame: bash's ${TW:-$FW}
            slices = ffv1_slices(runner.cores, r.fx.frame.width, r.fx.frame.height)
            args = [
                *_filtered([*inputs, *extra], r.passes.graph),
                *["-map", "0:a?"],
                *told.args,
                *attachment_args(carry=attached.carry),
                *kept,
                *tagged.args,  # after kept: its chapters, theirs
                *lossless_args(picture.codec, time_base=r.video.time_base, slices=slices),
                *audio_args(audio.codec, audio.encoder, audio.channels or 2),
                *cover.args,  # after the encoder: its -c:v:1 copy the cover's alone
                *container_flags(ext_of(str(r.target))),
                *r.passes.output,
            ]
    output.write(runner, r.target, args)


def _filtered(inputs: list[str], graph: Open) -> list[str]:
    """The inputs, the picture through ``graph``, mapped (bash: ``[$VSRC]$vf[v]``, ``-map [v]``)."""
    return [*inputs, *mapped(graph)]


def mapped(graph: Open) -> list[str]:
    """``graph`` closed into [v], and [v] mapped."""
    return ["-filter_complex", graph.close("v").render(), "-map", "[v]"]
