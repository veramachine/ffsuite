"""The YouTube flow: bash's convert --preset youtube -- two-pass H.264, the sound checked."""

import os
from pathlib import Path

from ffman.errors import refuse
from ffman.graph import Open
from ffman.jobs.convert import covers, output, subtitles, tagging
from ffman.jobs.convert.carried import own_folder
from ffman.media.paths import ext_of, file_url, resolve_output
from ffman.media.probe import read
from ffman.media.run import Runner, note
from ffman.plan.encode import attachment_args, youtube_args
from ffman.plan.request import ConvertOptions
from ffman.plan.streams import attachments, kept_metadata
from ffman.plan.youtube import (
    Copied,
    Silent,
    YouTubeSound,
    check_youtube_output,
    check_youtube_source,
    youtube_sound,
    youtube_video,
)


def run(o: ConvertOptions, runner: Runner) -> None:
    """YouTube's recommended upload (bash's convert): x264 High, two passes; AAC LC at 48 kHz."""
    media = read(o.input, runner)
    check_youtube_source(media, ext_of(o.input), o.input)
    target = resolve_output(
        o.input, o.output, in_place=o.in_place, overwrite=o.overwrite, default_ext="mp4"
    )
    check_youtube_output(ext_of(str(target)))
    tags = tagging.metadata_file(
        o, runner, media, "mp4"
    )  # after the flow's refusals, before any pass (F6)
    video = youtube_video(media, o.input)
    audio = youtube_sound(media, normalize=o.normalize, encoders=output.encoders(runner))
    extra, picked = _youtube_audio(o, runner, audio)
    note(video.note)
    source = ["-i", file_url(o.input)]
    # the picture alone (output v:0): -vf would filter a copied cover too, an ffmpeg error
    shown = ["-filter:v:0", Open(()).then(*video.filters).close().render()]
    time_base = media.video.time_base if media.video else None
    x264 = [*shown, *youtube_args(video.gop, video.kbps, time_base=time_base)]
    log = ["-passlogfile", str(runner.workdir / "x264")]
    first = [*source, "-map", "0:v:0", *x264, "-pass", "1", *log]
    runner.ffmpeg([*first, "-an", "-f", "null", "/dev/null"])  # the first pass: its log alone
    copied = ["-c:a", "copy"] if picked else []
    applied_input, mapped = kept_metadata([*source, *extra], tags.path)
    kept = [*mapped, "-use_editlist", "0"]
    mp4 = ["-movflags", "+faststart+negative_cts_offsets"]
    second = [*x264, "-pass", "2", *log, *copied, *kept, *mp4]
    inputs = [*source, *extra, *applied_input]
    trial_input, trial_kept = kept_metadata(source, tags.path)  # its own: no normalised audio yet
    trial = [*source, *trial_input, "-map", "0:v:0", *x264, *trial_kept, *mp4]
    labelled = tagging.tagging(runner, tagging.Given(media, o.input, tags.path), trial, "mp4")
    told = subtitles.kept(runner, media, file_url(o.input), "mp4")  # as every flow (3.12)
    attached = attachments(media, ext_of(o.input), "mp4")  # as every flow: one policy
    cover = covers.kept(runner, media, "mp4", covers.Job(file_url(o.input), tuple(trial), 1))
    for line in (
        *tags.notes,
        *told.notes,
        *cover.notes,
        *([attached.note] if attached.note else []),
        *labelled.notes,
    ):
        note(line)
    carried = [*told.args, *attachment_args(carry=attached.carry)]
    final = [
        *inputs,
        "-map",
        "0:v:0",
        *picked,
        *carried,
        *second,
        *cover.args,
    ]  # after x264: its copy
    output.write(runner, target, final)


def _youtube_audio(
    o: ConvertOptions, runner: Runner, audio: YouTubeSound
) -> tuple[list[str], list[str]]:
    """The sound's input and map: none, the source's, or ffmpeg-normalize's (run here)."""
    if isinstance(audio, Silent):
        note(audio.note)
        return [], []
    if isinstance(audio, Copied):
        return [], ["-map", "0:a:0"]
    preset, said = audio.preset, audio.note  # what is left: Normalised (the checker narrows it)
    # an XDG_CONFIG_HOME: the user's, else ffman's own (ffman/normalize, its presets)
    home = os.environ.get("FFMAN_NORMALIZE_HOME") or own_folder(runner, "normalize")
    if not (Path(home) / "ffmpeg-normalize" / "presets" / f"{preset}.json").is_file():
        refuse(f"missing ffmpeg-normalize preset {preset} in {home}")
    note(said)  # after the checks, as bash said it
    linked = runner.workdir / f"source.{ext_of(o.input)}"
    linked.symlink_to(os.path.realpath(o.input))  # bash: ln -s, under --dry-run too
    normalised = str(runner.workdir / "audio.m4a")
    tool = ["env", f"XDG_CONFIG_HOME={home}", "ffmpeg-normalize", str(linked)]
    argv = [*tool, "-vn", "-sn", "--preset", preset, "-o", normalised, "-f", "-q"]
    if runner.run(argv) != 0:
        refuse("ffmpeg-normalize failed")
    return ["-i", normalised], ["-map", "1:a:0"]
