"""Instant virtual type-split bundles.

A virtual split (``en_US_SV4_water``) is the physical set bundle with its CAB
renamed, so Unity treats it as a separate bundle.  The CAB name lives only in
the bundle's small directory ("block info", ~25 KB); the ~100 MB of card data
does not mention it.  The old path re-parsed and re-compressed the whole
bundle with UnityPy (~12 s of CPU per split) and kept every result on disk,
which needed ~80 GB for the 1,100+ splits players ask for.

This module rewrites only the directory and streams the original data blocks
straight from the set bundle: no build, no disk cache, no CPU.

``plan(src, new_cab)`` returns a ``SplitPlan`` or ``None`` when the bundle
layout isn't the simple one handled here (callers then fall back to the old
UnityPy worker).
"""
from __future__ import annotations

import os
import struct
import threading
from dataclasses import dataclass
from typing import Optional

try:  # UnityPy depends on lz4, so the server always has it.
    import lz4.block as _lz4
except Exception:  # pragma: no cover - only in stripped test environments
    _lz4 = None

_COMPRESSION_MASK = 0x3F
_INFO_AT_END = 0x80
_LZ4, _LZ4HC, _NONE = 2, 3, 0


@dataclass(frozen=True)
class SplitPlan:
    header: bytes        # rewritten bundle header
    data_start: int      # original data blocks: src[data_start:data_end]
    data_end: int
    tail: bytes          # rewritten directory, appended after the data
    src: str

    @property
    def length(self) -> int:
        return len(self.header) + (self.data_end - self.data_start) + len(self.tail)

    def stream(self, out, chunk: int = 256 * 1024) -> None:
        out.write(self.header)
        with open(self.src, 'rb') as handle:
            handle.seek(self.data_start)
            left = self.data_end - self.data_start
            while left > 0:
                piece = handle.read(min(chunk, left))
                if not piece:
                    raise IOError(f"{self.src} shrank while streaming")
                out.write(piece)
                left -= len(piece)
        out.write(self.tail)


def _lz4_decompress(data: bytes, size: int) -> bytes:
    if _lz4 is not None:
        return _lz4.decompress(data, uncompressed_size=size)
    dst = bytearray()
    i = 0
    while i < len(data):
        token = data[i]
        i += 1
        lit = token >> 4
        if lit == 15:
            while True:
                b = data[i]
                i += 1
                lit += b
                if b != 255:
                    break
        dst += data[i:i + lit]
        i += lit
        if i >= len(data):
            break
        off = data[i] | (data[i + 1] << 8)
        i += 2
        match = token & 15
        if match == 15:
            while True:
                b = data[i]
                i += 1
                match += b
                if b != 255:
                    break
        match += 4
        start = len(dst) - off
        if off >= match:
            dst += dst[start:start + match]
        else:
            for k in range(match):
                dst.append(dst[start + k])
    return bytes(dst)


def _read_cstr(buf: bytes, pos: int):
    end = buf.index(b'\0', pos)
    return buf[pos:end], end + 1


def _parse(src: str):
    """Header facts + decompressed directory, or None if unsupported."""
    file_size = os.path.getsize(src)
    with open(src, 'rb') as handle:
        head = handle.read(512)
        sig, pos = _read_cstr(head, 0)
        if sig != b'UnityFS':
            return None
        version = struct.unpack('>I', head[pos:pos + 4])[0]
        pos += 4
        _, pos = _read_cstr(head, pos)       # player version
        _, pos = _read_cstr(head, pos)       # engine revision
        fields_at = pos
        size, csz, usz, flags = struct.unpack('>qIII', head[pos:pos + 20])
        if size != file_size or not flags & _INFO_AT_END:
            return None
        comp = flags & _COMPRESSION_MASK
        if comp not in (_NONE, _LZ4, _LZ4HC):
            return None
        data_start = pos + 20
        if version >= 7:
            data_start = (data_start + 15) // 16 * 16
        data_end = file_size - csz
        handle.seek(data_end)
        raw = handle.read(csz)
    info = raw if comp == _NONE else _lz4_decompress(raw, usz)
    if len(info) != usz:
        return None
    return {
        'prefix': head[:fields_at], 'flags': flags, 'info': info,
        'data_start': data_start, 'data_end': data_end,
        'gap': head[fields_at + 20:data_start] if data_start > fields_at + 20 else b'',
    }


def _rename_nodes(info: bytes, new_cab: str) -> Optional[bytes]:
    """Rename the single CAB node in the directory; None if the layout has
    anything else (a .resS stream, several CABs, a different name length)."""
    q = 16
    blocks = struct.unpack('>i', info[q:q + 4])[0]
    q += 4 + 10 * blocks
    nodes = struct.unpack('>i', info[q:q + 4])[0]
    q += 4
    cab_spans = []
    for _ in range(nodes):
        q += 20
        name, end = _read_cstr(info, q)
        if name.startswith(b'CAB-'):
            cab_spans.append((q, name))
        q = end
    if len(cab_spans) != 1:
        return None
    at, old = cab_spans[0]
    new = new_cab.encode('ascii')
    if len(new) != len(old) or b'.' in old:
        return None
    return info[:at] + new + info[at + len(old):]


_CACHE: dict = {}
_CACHE_LOCK = threading.Lock()
_CACHE_MAX = 4096


def plan(src: str, new_cab: str) -> Optional[SplitPlan]:
    st = os.stat(src)
    key = (os.path.abspath(src), st.st_size, st.st_mtime_ns, new_cab)
    with _CACHE_LOCK:
        hit = _CACHE.get(key)
    if hit is not None:
        return hit
    parsed = _parse(src)
    if parsed is None:
        return None
    info = _rename_nodes(parsed['info'], new_cab)
    if info is None:
        return None
    # Store the ~25 KB directory uncompressed: Unity reads compression type 0
    # natively, and it keeps the output byte-for-byte predictable.
    flags = parsed['flags'] & ~_COMPRESSION_MASK
    tail = info
    data_len = parsed['data_end'] - parsed['data_start']
    total = len(parsed['prefix']) + 20 + len(parsed['gap']) + data_len + len(tail)
    header = (parsed['prefix']
              + struct.pack('>qIII', total, len(tail), len(info), flags)
              + parsed['gap'])
    result = SplitPlan(header, parsed['data_start'], parsed['data_end'], tail, src)
    with _CACHE_LOCK:
        if len(_CACHE) >= _CACHE_MAX:
            _CACHE.clear()
        _CACHE[key] = result
    return result
