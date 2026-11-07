"""Reject aliases and incomplete walks for local artifact inputs."""
import os
import stat
from collections.abc import Iterator
from pathlib import Path


def _checked_stat(path: Path) -> os.stat_result:
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
        raise ValueError("symlink_or_reparse_point_not_allowed")
    return info


def local_path(value: str | Path) -> Path:
    path = Path(value).expanduser().absolute()
    for part in (*reversed(path.parents), path):
        _checked_stat(part)
    return path.resolve(strict=True)


def _raise_walk_error(error: OSError) -> None:
    raise error


def iter_files(path: Path) -> Iterator[Path]:
    for root, dirs, files in os.walk(path, onerror=_raise_walk_error, followlinks=False):
        for name in dirs:
            _checked_stat(Path(root, name))
        dirs[:] = sorted(name for name in dirs if name not in {".git", ".morpheus", "__pycache__"})
        for name in sorted(files):
            file = Path(root, name)
            if stat.S_ISREG(_checked_stat(file).st_mode):
                yield file
