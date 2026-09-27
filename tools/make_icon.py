"""Draws the program icon (a dark-blue tile with a white person) as a Windows .ico with PNG images - standard library only.

    python tools/make_icon.py build/hr.ico
"""
import struct
import sys
import zlib


def png(size):
    bg, fg = (22, 32, 58, 255), (255, 255, 255, 255)
    rows = []
    r = size * 0.18  # corner radius
    for y in range(size):
        row = bytearray([0])
        for x in range(size):
            # rounded tile
            cx = min(max(x, r), size - 1 - r)
            cy = min(max(y, r), size - 1 - r)
            inside = (x - cx) ** 2 + (y - cy) ** 2 <= r * r
            px = bg if inside else (0, 0, 0, 0)
            # head and shoulders
            hx, hy, hr = size * 0.5, size * 0.36, size * 0.15
            if (x - hx) ** 2 + (y - hy) ** 2 <= hr * hr:
                px = fg
            bx, by, brx, bry = size * 0.5, size * 0.86, size * 0.28, size * 0.26
            if y < size * 0.84 and ((x - bx) / brx) ** 2 + ((y - by) / bry) ** 2 <= 1:
                px = fg
            row += bytes(px)
        rows.append(bytes(row))

    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(b"".join(rows), 9)) + chunk(b"IEND", b""))


def ico(sizes=(16, 32, 48, 256)):
    images = [png(s) for s in sizes]
    head = struct.pack("<HHH", 0, 1, len(images))
    offset = 6 + 16 * len(images)
    entries = b""
    for s, data in zip(sizes, images):
        entries += struct.pack("<BBBBHHII", s % 256, s % 256, 0, 0, 1, 32, len(data), offset)
        offset += len(data)
    return head + entries + b"".join(images)


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "hr.ico"
    with open(target, "wb") as fh:
        fh.write(ico())
    print(target)
