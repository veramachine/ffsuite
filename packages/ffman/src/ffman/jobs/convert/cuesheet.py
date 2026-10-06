"""A source FLAC's CUESHEET block, carried into a FLAC output (spec 3.13) -- ffmpeg drops it.

Carried, never made from chapters (the owner's decision): a FLAC holding both the block
and CHAPTERxxx comments reads back, in ffmpeg and so mpv, as untitled chapters -- flacdec
makes the block's tracks chapters by track number, and avpriv_new_chapter overwrites the
comments' of the same id (measured). The source's own block was so before.
"""

import shutil
from collections.abc import Callable

from ffman.errors import refuse
from ffman.media import flac
from ffman.media.run import Runner, missing, note


def finisher(runner: Runner, source: str, *, replaced: bool) -> Callable[[str], None]:
    """The step carrying ``source``'s CUESHEET block into a FLAC partial, if it has one.

    Found by ffman itself (``media.flac``): metaflac is asked only for a block there, and is
    optional -- absent, the block is noted left out and the job done; failing, refused. Left
    out, noted, when ``replaced`` (--metadata's chapters stand for it; metaflac then not
    needed). Its offsets stay
    true: a FLAC into FLAC is a remux, its samples the source's -- re-encoded losslessly, the
    same count (measured), never trimmed nor resampled.
    """

    def finish(partial: str) -> None:
        if not flac.has_cuesheet(source):  # ffman's own read: metaflac never asked for none
            return
        if replaced:
            note("the source's CUESHEET block: --metadata's chapters replace it: left out")
            return
        if shutil.which("metaflac") is None:  # optional (spec 3.13): the job done without it
            note(f"the source's CUESHEET block: {missing('metaflac')}: left out")
            return
        block = runner.capture(["metaflac", "--export-cuesheet-to=-", source])  # a check: dry too
        if block.returncode != 0:  # a block is there: its loss is no silence
            refuse("metaflac failed (its message is above)")
        cue = runner.workdir / "cuesheet.cue"
        if not runner.dry_run:
            _ = cue.write_text(block.stdout, encoding="utf-8")
        if runner.run(["metaflac", f"--import-cuesheet-from={cue}", partial]) != 0:
            refuse("metaflac failed (its message is above)")

    return finish
