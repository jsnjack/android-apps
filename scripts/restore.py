#!/usr/bin/env python3
"""Safely restore a previous publication ZIP downloaded from this repository."""

from pathlib import Path, PurePosixPath
import sys
import zipfile


def restore(archive, output):
    with zipfile.ZipFile(archive) as bundle:
        for member in bundle.infolist():
            path = PurePosixPath(member.filename)
            if path.is_absolute() or ".." in path.parts or "\\" in member.filename:
                raise ValueError(f"Unsafe archive path: {member.filename}")
            if member.file_size > 256 * 1024 * 1024:
                raise ValueError("Unexpectedly large publication file")
        bundle.extractall(output)


if __name__ == "__main__":
    restore(Path(sys.argv[1]), Path(sys.argv[2]))
