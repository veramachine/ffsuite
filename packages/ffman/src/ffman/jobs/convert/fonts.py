"""Where libass finds ffman's fonts: IBM Plex Sans, the captions'; Plex Mono Bold, the stamp's.

``FFMAN_FONTS_DIR`` if set; else ffman's own copy (``ffman/fonts``: IBM's 1.1.0 release,
unmodified, as nixpkgs' ``ibm-plex`` -- byte for byte), as a path ffmpeg's filter syntax
takes; a copy whose path it would split (a venv under a spaced folder) or held in a zip is
written into the job's work directory, whose path is safe. A folder lacking the font is
noted once a job, when the job draws with it: libass then takes fontconfig's -- the system's own,
if installed (measured: rendered a little apart all the same), else a substitute.
"""

import os
from pathlib import Path
from typing import Final
from weakref import WeakKeyDictionary

from ffman.effects.camcorder import STAMP_FILE, STAMP_FONT
from ffman.errors import refuse
from ffman.jobs.convert.carried import own_folder
from ffman.media.run import Runner, note
from ffman.subs.ass import FONT, FONT_FILES
from ffman.values import is_safe_path

_CARRIED: Final = {  # each family ffman carries: its files, and what a job gets without them
    FONT.lower(): (
        FONT,
        tuple(FONT_FILES.values()),
        "the system's font in its place, line widths estimated",
    ),
    STAMP_FONT.lower(): (STAMP_FONT, (STAMP_FILE,), "the system's font in its place"),
}
_FOLDERS: Final[WeakKeyDictionary[Runner, str]] = WeakKeyDictionary()  # a job's folder, found once
_TOLD: Final[WeakKeyDictionary[Runner, set[str]]] = WeakKeyDictionary()  # its families told missing


def fonts_dir(runner: Runner, family: str) -> str:
    """The fonts folder handed to libass for ``runner``'s job; refused where filters split it.

    ``family``, the font the job draws with: one ffman carries, missing from the folder, is
    noted, once a job -- another (``--font``'s) comes from fontconfig either way.
    """
    if (folder := _FOLDERS.get(runner)) is None:
        folder = _found(runner)
        _FOLDERS[runner] = folder
    carried = _CARRIED.get(family.lower())  # libass: ass_strcasecmp, as font_metrics compares
    if carried is not None:
        name, files, without = carried
        told = _TOLD.setdefault(runner, set())
        if name not in told and not all((Path(folder) / file).is_file() for file in files):
            note(f"{name} not in {folder}: {without}")
            told.add(name)
    return folder


def _found(runner: Runner) -> str:
    given = os.environ.get("FFMAN_FONTS_DIR")
    if given:
        if not is_safe_path(given):
            refuse(f"FFMAN_FONTS_DIR has characters ffmpeg's filter syntax would split on: {given}")
        return given
    return own_folder(runner, "fonts", is_safe_path)
