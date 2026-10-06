"""The burn flow: bash's overlay -- subtitles drawn in, in the bar when there is one."""

import re
import shutil
from collections import Counter
from dataclasses import replace
from fractions import Fraction
from pathlib import Path
from typing import Final

from subverter.transcript import Transcript

from ffman.effects.stages import Effects, check_restorable
from ffman.errors import refuse
from ffman.graph import Filter, Labels, Open
from ffman.graph.resize import Picture, blurred_fit, head
from ffman.jobs.convert import passes, render, tagging
from ffman.jobs.convert.fonts import fonts_dir
from ffman.media.paths import ext_of, read_file, resolve_output
from ffman.media.probe import Media, read
from ffman.media.run import Runner, ffmpeg_args, note
from ffman.plan.geometry import displayed, picture_stream, target_size
from ffman.plan.outputs import Output, check_burn_source, output_kind
from ffman.plan.request import ConvertOptions
from ffman.subs.ass import FONT, FONT_FILES, Style, bold
from ffman.subs.ass import script as ass_script
from ffman.subs.ingest import ingest
from ffman.subs.layout import Bar, BarKind, bar_args, bar_centre, bar_rows, bar_times
from ffman.subs.metrics import Metrics, parse

# bash's _SAFE_PATH: nothing in it that ffmpeg's filter syntax would split on
_SAFE_PATH: Final = re.compile(r"[A-Za-z0-9_./+@-]+")


def run(o: ConvertOptions, subs: str, runner: Runner) -> None:
    """Subtitles burned in (bash's overlay): resized, its effects, the text drawn after them."""
    media = read(o.input, runner)
    video = picture_stream(media.video, o.input)
    source = displayed(video, o.input)
    check_burn_source(ext_of(o.input), o.input)
    # decided, and refused, before any work: from the options and the probe
    target = resolve_output(o.input, o.output, in_place=o.in_place, overwrite=o.overwrite)
    out_ext = ext_of(str(target))
    kind = output_kind(o, burn=True, moving=True, out_ext=out_ext)
    tags = tagging.metadata_file(
        o, runner, media, out_ext
    )  # after the flow's refusals, before any pass (F6)
    restore = kind is Output.VIDEO  # the effects give the picture its format back
    check_restorable(o.effects, video, restore=restore)
    fonts = fonts_dir(runner, o.font)
    size = target_size(source, video=True, width=o.width, height=o.height, aspect=o.aspect_text)
    transcript = ingest(subs, read_file(subs))
    for line in transcript.notes:
        note(line)
    _check_timings(o, transcript)
    encoded = render.encoding(o, runner, media, kind, out_ext)  # this ffmpeg's encoders: asked last
    if size is not None and size.note:
        note(size.note)
    labels = Labels()
    headed = Open(("0:v:0",))
    picture = Picture(source, size, video, moving=True) if size is not None else None
    if picture is not None:
        headed, blur_note = head(o.resize_mode, o.bblur, picture, labels)
        if blur_note:
            note(blur_note)
    fx = Effects(
        o.effects, passes.camcorder(o, runner, media, passes.frame_for(source, size, video)), labels
    )
    shown = (size.width, size.height) if size is not None else (source.width, source.height)
    bar = None
    if not o.margin_bottom_given and transcript.fmt not in ("ass", "ssa"):
        bar = _bar(o, runner, media, picture, shown[1])
    bar_y = bar.y if bar is not None else None
    style = Style(
        mode=o.overlay_mode,
        highlight=o.highlight_mode,
        size=o.font_size,
        margin=o.margin_bottom,
        bar_y=bar_y,
        font=o.font,
        colorize=o.highlight_colorize,
        text=o.font_color,
        outline=o.outline_color,
    )
    subtitles = _subtitles(subs, runner, transcript, shown, style, fonts, frame=video.frame_time())
    fx = replace(fx, subtitles=subtitles)
    prepared = passes.effects(o, runner, fx, headed, restore=restore)
    render.run(o, runner, render.Render(target, encoded, media, video, fx, prepared, tags))


def _check_timings(o: ConvertOptions, t: Transcript) -> None:
    """What the mode needs of the transcript (bash's overlay, after ingest_subs)."""
    mode = o.overlay_mode
    if t.fmt in ("ass", "ssa") and mode != "plain":
        refuse(f"an .{t.fmt} file can only be burned with --overlay-mode plain")
    if mode == "chunk-word":
        if not t.has_words:
            sources = "whisper-cli -ojf JSON, WhisperX JSON, or WhisperX --highlight_words srt/vtt"
            refuse(f"--overlay-mode chunk-word needs word timings ({sources}); {t.source} has none")
        counts = Counter(w.segment for w in t.words)
        worded = sum(1 for n in counts.values() if n > 1)  # sentences with more than one word
        if not counts or worded / len(counts) < 0.2:  # noqa: PLR2004 -- bash's fifth
            why = "--overlay-mode chunk-word needs sentences with their words"
            refuse(f"this {t.source} is word-level (e.g. whisper-cli -sow/-ml 1): {why}")
    spaced = any(" " in c.text for c in t.chunks)  # a cue of more than one word
    if mode in ("word", "word-highlight") and not t.has_words and spaced:
        tools = "whisper-cli -sow -ml 1 or -ojf, WhisperX JSON or --highlight_words"
        why = f"--overlay-mode {mode} needs word timings or one word per cue"
        refuse(f"{why}; {t.source} has neither ({tools})")


def _bar(
    o: ConvertOptions, runner: Runner, media: Media, picture: Picture | None, height: int
) -> Bar | None:
    """A bar under the picture the text will sit on (bash's bottom_bar): read-only passes.

    What is black under the picture, the frames read through the resize alone
    (``detection_chain``): the source's own bars and the resize's. A fit's blurred bars are
    the resize's, so say so. ``height`` is the planned frame's -- the one the ASS is drawn for,
    which the chain makes (bash read it from ffmpeg's log: 360 in the tests).
    """
    blurred = picture is not None and blurred_fit(o.resize_mode, o.bblur)
    bar = _detected(
        o, runner, media, detection_chain(o, picture), height, "blurred" if blurred else "black"
    )
    if bar is not None:
        note(bar.note)
    return bar


def _detected(  # noqa: PLR0913 -- the job, its media, the chain, the frame's height, its bar's kind
    o: ConvertOptions, runner: Runner, media: Media, chain: str, height: int, kind: BarKind
) -> Bar | None:
    """What is black under the picture, sampled through ``chain``: the lowest row with picture."""
    duration = media.duration
    if duration is None and media.video is not None:
        duration = media.video.duration
    times, frames = bar_times(duration)
    printed = ""
    for at in times:  # a sample that fails prints nothing (bash: || true)
        args = ffmpeg_args(bar_args(o.input, at, frames, chain), runner.cores)
        printed += runner.capture(["ffmpeg", "-hide_banner", "-nostdin", *args]).stdout
    lowest = bar_rows(printed)
    return bar_centre(height, lowest, o.font_size, kind) if lowest is not None else None


def detection_chain(o: ConvertOptions, picture: Picture | None) -> str:
    """The picture the text will sit on, as a -vf prefix: "" or "FILTERS," (bash's det).

    The resize alone, its blurred bars filled black (``measure``): the bar is the picture's
    geometry -- the source's and the resize's -- and no effect before the text moves it, while
    they recolour it (bash read it after them: an inverted bar went unseen, a blur's spill
    took 6 rows of 92). Built from an unlabelled start, as bash's text was: the head's own
    first chain then reads -vf's input (its note was given with the render's head).
    """
    det = Open(())
    if picture is not None:
        det, _ = head(o.resize_mode, o.bblur, picture, Labels(), det, measure=True)
    return _vf(det)


def _vf(graph: Open) -> str:
    """A graph as a -vf prefix: "" or "FILTERS,"."""
    return f"{graph.close().render()}," if graph.filters or graph.chains else ""


def font_metrics(fonts: str, style: Style) -> Metrics | None:
    """The shipped font's metrics for the style's weight; None: its lines estimated.

    None for another font (libass finds it, ffman cannot) or a font file missing or unreadable.
    """
    if not fonts or style.font.lower() != FONT.lower():  # libass: ass_strcasecmp
        return None
    try:
        return parse((Path(fonts) / FONT_FILES[bold(style)]).read_bytes())
    except (OSError, ValueError):
        return None


def _subtitles(  # noqa: PLR0913 -- the subtitles, where, what, how big, how, with which fonts
    subs: str,
    runner: Runner,
    t: Transcript,
    shown: tuple[int, int],
    style: Style,
    fonts: str,
    *,
    frame: Fraction | None,
) -> Filter:
    """The ASS to burn -- written, or the user's own copied -- and its filter, fonts and all."""
    if t.fmt in ("ass", "ssa"):
        path = runner.workdir / f"subs.{t.fmt}"
        _ = shutil.copyfile(subs, path)
    else:
        # the source's frames: a burn keeps them, so its words' animations end a frame early
        text, notes = ass_script(t, *shown, style, frame=frame, metrics=font_metrics(fonts, style))
        path = runner.workdir / "subs.ass"
        _ = path.write_text(text)
        for said in notes:
            note(said)
    return Filter("ass", (("filename", str(path)), *((("fontsdir", fonts),) if fonts else ())))
