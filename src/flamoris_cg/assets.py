"""Resolve explicitly supplied local PNG assets; scene JSON contains only IDs."""
import struct
from pathlib import Path

from .spec import _id


def resolve_png(asset_root, asset_id):
    _id(asset_id)
    if asset_root is None:
        raise ValueError("sprite requires explicit --assets directory")
    root = Path(asset_root).resolve(strict=True)
    path = (root / (asset_id + ".png")).resolve(strict=True)
    if not path.is_relative_to(root):
        raise ValueError("sprite asset escapes asset directory")
    if not path.is_file() or path.stat().st_size > 16 * 1024 * 1024:
        raise ValueError("sprite PNG must be a file <= 16 MiB")
    with path.open("rb") as stream:
        header = stream.read(33)
    if len(header) != 33 or header[:16] != b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR":
        raise ValueError("sprite asset must be a PNG")
    width, height = struct.unpack(">II", header[16:24])
    if not (1 <= width <= 4096 and 1 <= height <= 4096):
        raise ValueError("sprite dimensions must be 1..4096")
    if width * height > 8_388_608:
        raise ValueError("sprite pixel budget exceeded")
    return path
