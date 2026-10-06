"""The resize flow: bash's convert -w/-H/-a, effects, a GIF or a still."""

from ffman.effects.stages import Effects, check_restorable
from ffman.graph import Labels, Open
from ffman.graph.resize import Picture, head
from ffman.jobs.convert import passes, render, tagging
from ffman.media.paths import ext_of, resolve_output
from ffman.media.probe import read
from ffman.media.run import Runner, note
from ffman.plan.geometry import displayed, picture_stream, target_size
from ffman.plan.outputs import Output, check_moving, is_image, output_kind
from ffman.plan.request import ConvertOptions


def run(o: ConvertOptions, runner: Runner) -> None:
    """The resize (bash's): the picture resized, its effects, encoded as it was; the rest kept."""
    media = read(o.input, runner)
    video = picture_stream(media.video, o.input)
    source = displayed(video, o.input)
    in_ext = ext_of(o.input)
    moving = not is_image(in_ext)
    target = resolve_output(o.input, o.output, in_place=o.in_place, overwrite=o.overwrite)
    out_ext = ext_of(str(target))
    kind = output_kind(o, burn=False, moving=moving, out_ext=out_ext)
    tags = tagging.metadata_file(
        o, runner, media, out_ext
    )  # after the flow's refusals, before any pass (F6)
    size = target_size(source, video=moving, width=o.width, height=o.height, aspect=o.aspect_text)
    if size is not None and size.note:
        note(size.note)
    check_moving(o, moving=moving)
    restore = kind is Output.VIDEO  # the effects give the picture its format back
    check_restorable(o.effects, video, restore=restore)
    encoded = render.encoding(o, runner, media, kind, out_ext)
    labels = Labels()
    headed = Open(("0:v:0",))
    if size is not None:  # bash: no size, no head -- the effects see the frame as it is
        headed, blur_note = head(
            o.resize_mode, o.bblur, Picture(source, size, video, moving), labels
        )
        if blur_note:
            note(blur_note)
    fx = Effects(
        o.effects, passes.camcorder(o, runner, media, passes.frame_for(source, size, video)), labels
    )
    prepared = passes.effects(o, runner, fx, headed, restore=restore)
    render.run(o, runner, render.Render(target, encoded, media, video, fx, prepared, tags))
