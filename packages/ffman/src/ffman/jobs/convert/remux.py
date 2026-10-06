"""A remux (spec 3.11): another container, a codec, or a metadata file -- the rest copied.

Each stream as it is unless a codec is asked for; whether the output holds them, asked
of ffmpeg before any work (``output.holds``). An attached picture is not carried: a
cover is a stream of its own decision.
"""

from ffman.errors import refuse
from ffman.jobs.convert import covers, cuesheet, output, subtitles, tagging
from ffman.media.paths import ext_of, file_url, resolve_output
from ffman.media.probe import Media, read
from ffman.media.run import Runner, note
from ffman.plan.encode import attachment_args, audio_args, container_flags
from ffman.plan.outputs import Output, output_kind
from ffman.plan.request import ConvertOptions
from ffman.plan.streams import attachments, kept_metadata, lossless, sound


def run(o: ConvertOptions, runner: Runner) -> None:
    """The input's streams into the output's container: copied, or as asked."""
    target = resolve_output(o.input, o.output, in_place=o.in_place, overwrite=o.overwrite)
    ext = ext_of(str(target))
    if output_kind(o, burn=False, moving=True, out_ext=ext) is not Output.VIDEO:
        refuse(f"convert: a .{ext} is a picture made anew: give a size (-w, -H, -a) or an effect")
    media = read(o.input, runner)
    found = output.encoders(runner)
    attached = attachments(media, ext_of(o.input), ext)
    told = subtitles.kept(runner, media, file_url(o.input), ext)
    inputs = ["-i", file_url(o.input)]
    metadata = tagging.metadata_file(o, runner, media, ext)
    applied = metadata.path
    extra, kept = kept_metadata(inputs, applied)
    if ext == "flac" and media.video is not None and o.video_codec is not None:  # a picture asked
        refuse(f"--video-codec {o.video_codec}: a .flac holds pictures as covers alone")
    if ext == "flac" and media.video is not None:  # flacenc.c: "not an attached picture. Ignoring"
        picture, dropped = (
            [],
            f"the picture ({media.video.codec}): a .flac holds covers alone: left out",
        )
    else:
        picture, dropped = _picture(o, runner, media, found, same=ext == ext_of(o.input)), None
    heard = sound(o, media, found)
    sounds = ["-map", "0:a?", *audio_args(heard.codec, heard.encoder, heard.channels or 2)]
    held = (
        *inputs,
        *extra,
        *picture,
        *sounds,
        *told.args,
        *attachment_args(carry=attached.carry),
        *kept,
        *container_flags(ext),
    )
    job = covers.Job(
        file_url(o.input), held, media.pictures, len(media.attachments) if attached.carry else 0
    )
    cover = covers.kept(runner, media, ext, job)
    rest = [
        *told.args,
        *attachment_args(carry=attached.carry),
        *cover.args,
        *kept,
        *container_flags(ext),
    ]
    held = (
        output.Held(
            "video", picture, output.named(o.video_codec, media.video), o.video_codec is not None
        ),
        output.Held(
            "audio", sounds, output.named(o.audio_codec, media.audio), o.audio_codec != "copy"
        ),
    )
    output.check_held(runner, ext, [*inputs, *extra], held, rest)  # every input the job has
    whole = [*inputs, *extra, *picture, *sounds, *rest]
    given = tagging.Given(media, o.input, applied)
    tagged = tagging.tagging(runner, given, whole, ext)
    for line in (
        *metadata.notes,
        *([dropped] if dropped else []),
        *told.notes,
        *cover.notes,
        *([attached.note] if attached.note else []),
        *tagged.notes,
    ):
        note(line)
    finish = None
    if ext == "flac" and ext_of(o.input) == "flac":  # its CUESHEET block, carried (3.13)
        finish = cuesheet.finisher(runner, o.input, replaced=applied is not None)
    output.write(runner, target, [*whole, *tagged.args], finish)  # after kept: its chapters


def _picture(
    o: ConvertOptions, runner: Runner, media: Media, found: frozenset[str], *, same: bool
) -> list[str]:
    """The picture copied, or encoded as 3.3's when asked.

    Into its own container, copied whole -- an attached picture (a cover) and data streams
    (MP4's timecode) too, as a plain copy keeps them; elsewhere the picture alone (``0:V``):
    a cover or a data stream is not every container's.
    """
    if o.video_codec is None and not o.lossless:  # nothing asked of the picture
        whole = (
            ["-map", "0:V?", "-map", "0:d?", "-c:d", "copy"] if same else ["-map", "0:V?"]
        )  # covers: 3.15
        return [*whole, "-c:v", "copy"]
    return output.lossless_picture(runner, media, lossless(o, media, found).codec)
