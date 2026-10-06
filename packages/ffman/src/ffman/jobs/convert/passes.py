"""What the effects need before the render: their frame, the camcorder's script, their passes."""

from dataclasses import replace
from datetime import datetime

from ffman.effects.camcorder import STAMP_FONT, clock, script, width
from ffman.effects.datamosh import MOSH_CODEC, SCENE_CUTS, cuts, mosh
from ffman.effects.dither import dithered, palette_graph
from ffman.effects.frame import Frame, Stamp
from ffman.effects.spec import Request
from ffman.effects.stages import ALL, STAGE_A, STAGE_B, Effects, before_dither, chain
from ffman.graph import Open
from ffman.graph.sizes import Displayed, Target
from ffman.jobs.convert import render
from ffman.jobs.convert.fonts import fonts_dir
from ffman.media.paths import file_url
from ffman.media.probe import Media, Video
from ffman.media.run import Runner, ffmpeg_args, note
from ffman.plan.request import ConvertOptions


def frame_for(source: Displayed, size: Target | None, video: Video) -> Frame:
    """What the effects are sized by (bash's fx_chain arguments and FX_SAR).

    The target after a resize, which squares the pixels (FX_SAR 1); else the
    frame as stored, turned, with its own SAR.
    """
    if size is not None:
        return Frame.resized(size.width, size.height, video)
    return Frame(source.frame_width, source.frame_height, source.sar, video)


def camcorder(o: ConvertOptions, runner: Runner, media: Media, frame: Frame) -> Frame:
    """The camcorder's script written, when it runs (bash's cam_prepare), and the frame told."""
    stamp = _requested(o, "camcorder")
    if stamp is None:
        return frame
    now = datetime.now()  # noqa: DTZ005 -- bash's date: local wall-clock time, read as UTC
    start = clock(media.creation_time, stamp.values.get("date"), stamp.values.get("time"), now)
    path = runner.workdir / "camcorder.ass"
    _ = path.write_text(script(start, media.duration, width(frame.width, frame.height)))
    return replace(frame, camcorder=Stamp(str(path), fonts_dir(runner, STAMP_FONT)))


def effects(
    o: ConvertOptions, runner: Runner, fx: Effects, headed: Open, *, restore: bool
) -> render.Passes:
    """The mosh and palette passes, as bash ran them (mosh_prepare, fx_palette), and the chain."""
    inputs: list[str] = []
    output: list[str] = []
    start, stages, reads = headed, ALL, file_url(o.input)
    mosh_request = _requested(o, "datamosh")
    if mosh_request is not None:
        moshed = runner.workdir / "mosh.mkv"
        picture = before_dither(fx, headed, STAGE_A)  # the head, the picture's and the lens's
        seconds = mosh_request.values.get("seconds")
        heal = None if seconds in (None, "auto") else seconds
        plan = mosh(_scene_cuts(runner, o.input, picture), heal, fx.frame.video.avg_frame_rate)
        keys = ["-force_key_frames", plan.keys] if plan.keys else []
        melt = [*MOSH_CODEC, *keys, "-bsf:v", plan.drop, str(moshed)]
        runner.ffmpeg(["-i", file_url(o.input), *render.mapped(picture), *melt])
        output = plan.output
        inputs += ["-i", str(moshed)]
        start, stages, reads = Open(("1:v:0",)), STAGE_B, file_url(moshed)
    colours = dithered(o.effects)
    palette = None
    if colours is not None:
        palette = f"{1 + len(inputs) // 2}:v"
    graph = chain(fx, start, restore=restore, stages=stages, palette=palette)
    if colours is not None:  # after the chain, before the render, as bash's fx_palette
        before = before_dither(fx, Open(("0:v:0",)) if mosh_request else headed, stages)
        made = palette_graph(before, colours).render()
        path = str(runner.workdir / "palette.png")
        runner.ffmpeg(
            ["-i", reads, "-filter_complex", made, "-map", "[p]", *render.ONE_FRAME, path]
        )
        inputs += ["-i", path]
    return render.Passes(inputs, graph, output)


def _scene_cuts(runner: Runner, path: str, picture: Open) -> list[str]:
    """The scene cuts, found on the picture the mosh melts (read-only: --dry-run runs it too)."""
    analysis = ["-i", file_url(path), "-filter_complex", picture.then(SCENE_CUTS).close().render()]
    argv = [
        "ffmpeg",
        "-hide_banner",
        "-nostdin",
        *ffmpeg_args([*analysis, "-f", "null", "-"], runner.cores),
    ]
    found = cuts(runner.capture(argv).stderr)  # bash: || true -- a failed analysis finds none
    if not found:
        note("--datamosh: no scene cut found, so nothing melts")
    return found


def _requested(o: ConvertOptions, name: str) -> Request | None:
    return next((r for r in o.effects if r.effect.name == name), None)
