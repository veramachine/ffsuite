"""Where a job writes: the output path, and the partial file it becomes.

Stage A keeps the bash ffman's rules (``resolve_output`` and ``finish``): the
extension picks the container, an existing output needs ``--overwrite``, a
replaced input is replaced through its real path, and every write goes to a
hidden partial beside the output, renamed into place only once complete. New:
the default name (``STEM.ffman.EXT``) and ``--in-place``, the one way to
replace the input.
"""

import os
import stat
import tempfile
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from ffman.errors import refuse


def file_url(path: str | os.PathLike[str]) -> str:
    """``path`` as ffmpeg must open it: by the file protocol, whatever it is named.

    ffmpeg reads a name's leading [A-Za-z0-9+-.] run before a ``:`` as a protocol
    (``a:b.mp4`` is protocol ``a``, unknown; ``http:x`` is HTTP), and its file protocol
    takes one ``file:`` off (libavformat/avio.c url_find_protocol, file.c; n8.1.2).
    For every path a user names; the paths ffman makes are absolute (mkstemp,
    mkdtemp), which no protocol can claim.
    """
    return f"file:{os.fspath(path)}"


def read_file(path: str) -> bytes:
    """An input file's bytes; refused when there is no such file (a directory is none)."""
    try:
        return Path(path).read_bytes()
    except (FileNotFoundError, IsADirectoryError):
        refuse(f"no such file: {path}")


def ext_of(path: str) -> str:
    """The extension of ``path``'s file name, lowercased; "" when it has none (bash ``ext_of``)."""
    name = path.rsplit("/", 1)[-1]
    return name.rsplit(".", 1)[1].lower() if "." in name else ""


def same_file(a: str, b: str) -> bool:
    """Whether ``a`` and ``b`` name one file (``realpath -m``: need not exist)."""
    return os.path.realpath(a) == os.path.realpath(b)


def resolve_output(
    input_path: str,
    output: str | None,
    *,
    in_place: bool,
    overwrite: bool,
    default_ext: str | None = None,
) -> Path:
    """The path the job writes; refuses what the spec refuses. No side effects."""
    if in_place:
        target = Path(os.path.realpath(input_path))
        if not ext_of(str(target)):  # as for any output: the extension picks the container
            refuse(f"output needs an extension (it selects the container): {input_path}")
        return target
    if output is None:
        folder, slash, name = input_path.rpartition("/")  # "/x.mp4" keeps its "/"
        stem = name.rsplit(".", 1)[0] if "." in name else name
        ext = default_ext if default_ext is not None else ext_of(input_path)
        output = f"{folder}{slash}{stem}.ffman.{ext}"
    _extension(output)
    if same_file(input_path, output):
        refuse(f"the output is the input: use --in-place to replace it: {output}")
    _absent(output, overwrite=overwrite)
    return Path(output)


def new_output(output: str, *, overwrite: bool) -> Path:
    """The path a job with no input writes (meta's new file), refused as ``resolve_output``'s."""
    _extension(output)
    _absent(output, overwrite=overwrite)
    return Path(output)


def _extension(output: str) -> None:
    if not ext_of(output):
        refuse(f"output needs an extension (it selects the container): {output}")


def _absent(output: str, *, overwrite: bool) -> None:
    if Path(output).exists() and not overwrite:
        refuse(f"output exists: {output} (use --overwrite to replace it)")


@contextmanager
def partial_output(target: Path) -> Generator[Path]:
    """Yield a hidden file beside ``target`` to write; on success, it becomes ``target``.

    On any exception the partial is removed and the exception goes on. A partial
    left empty is refused ("ffmpeg produced no output"). The result takes the
    replaced file's permissions, or 0666 less the umask for a new one.
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    handle, name = tempfile.mkstemp(
        prefix=".ffman.", suffix=f".{ext_of(str(target))}", dir=target.parent
    )
    os.close(handle)
    partial = Path(name)
    try:
        yield partial
        if partial.stat().st_size == 0:
            refuse("ffmpeg produced no output")
        partial.chmod(stat.S_IMODE(target.stat().st_mode) if target.exists() else 0o666 & ~_umask())
        _ = partial.replace(target)
    finally:
        partial.unlink(missing_ok=True)


def _umask() -> int:
    # Reading the umask means setting it: safe, as ffman is single-threaded.
    mask = os.umask(0)
    _ = os.umask(mask)
    return mask
