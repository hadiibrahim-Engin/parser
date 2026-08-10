"""Generate the Windows application icon from the bundled SVG mark.

The icon is built rather than committed so it can never drift from the logo the
interface actually draws. Qt renders the PNG sizes; the ICO container is packed
here because Qt's image plugins do not write ICO.
"""

from __future__ import annotations

import os
import struct
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QBuffer, QIODevice  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from cgmesparser.gui.resources.icons import iconPixmap  # noqa: E402
from cgmesparser.gui.resources.tokens import TOKENS  # noqa: E402

SIZES = (16, 24, 32, 48, 64, 128, 256)

_ICONDIR = "<HHH"  # reserved, type, image count
_ICONDIRENTRY = "<BBBBHHII"  # width, height, colours, reserved, planes, bpp, size, offset


def renderPng(size: int) -> bytes:
    """One square PNG of the application mark."""
    pixmap = iconPixmap("tower", TOKENS.primary, size, 1.0)
    # QBuffer with no argument owns its storage. Handing it a temporary
    # QByteArray instead leaves it pointing at freed memory.
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    pixmap.save(buffer, "PNG")
    buffer.close()
    return bytes(buffer.data())


def packIco(images: dict[int, bytes]) -> bytes:
    """Pack PNG images into an ICO container."""
    count = len(images)
    offset = struct.calcsize(_ICONDIR) + count * struct.calcsize(_ICONDIRENTRY)

    directory = bytearray(struct.pack(_ICONDIR, 0, 1, count))
    payload = bytearray()

    for size, data in sorted(images.items()):
        # 256 is stored as 0; the format has only one byte for each dimension.
        dimension = 0 if size >= 256 else size
        directory += struct.pack(_ICONDIRENTRY, dimension, dimension, 0, 0, 1, 32, len(data), offset)
        payload += data
        offset += len(data)

    return bytes(directory + payload)


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: makeIcon.py <output.ico>", file=sys.stderr)
        return 2

    target = Path(argv[1])
    target.parent.mkdir(parents=True, exist_ok=True)

    QApplication(["makeIcon"])
    target.write_bytes(packIco({size: renderPng(size) for size in SIZES}))

    print(f"wrote {target} ({target.stat().st_size:,} bytes, {len(SIZES)} sizes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
