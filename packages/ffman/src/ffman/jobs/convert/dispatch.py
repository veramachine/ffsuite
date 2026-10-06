"""Which flow a convert job is, and running it."""

from ffman.jobs.convert import attach, burn, metadata, remux, resize, youtube
from ffman.media.run import Runner, require
from ffman.plan.flows import Flow, select_flow
from ffman.plan.request import ConvertOptions


def convert(o: ConvertOptions, runner: Runner) -> None:
    """Run the job ``o`` asks for."""
    flow = select_flow(o)
    if flow is not Flow.METADATA:  # metadata files alone need neither (spec 1, 3.9)
        require("ffmpeg", "ffprobe")  # before any work
    if flow is Flow.METADATA:
        metadata.run(o, runner)
        return
    if flow is Flow.YOUTUBE:
        youtube.run(o, runner)
        return
    if flow is Flow.TRACKS:
        attach.run(o, runner)
        return
    if flow is Flow.REMUX:
        remux.run(o, runner)
        return
    if o.burn_subs is not None:
        burn.run(o, o.burn_subs, runner)
        return
    resize.run(o, runner)
