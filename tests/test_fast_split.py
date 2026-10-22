"""Virtual type-split bundles served by rewriting only the bundle directory."""
import io
import os
import struct
import tempfile
import unittest

from spirit.server import fast_split

OLD = b'CAB-' + b'a' * 32
NEW = 'CAB-' + 'b' * 32


def _bundle(nodes, data=b'x' * 1000, info_at_end=True):
    blocks = struct.pack('>IIH', len(data), len(data), 0)
    node_bytes = b''.join(struct.pack('>qqI', 0, len(data), 4) + n + b'\0' for n in nodes)
    info = b'\0' * 16 + struct.pack('>i', 1) + blocks + struct.pack('>i', len(nodes)) + node_bytes
    prefix = b'UnityFS\0' + struct.pack('>I', 6) + b'5.x.x\0' + b'2018.4.11f1\0'
    flags = 0x40 | (0x80 if info_at_end else 0)
    total = len(prefix) + 20 + len(data) + len(info)
    return prefix + struct.pack('>qIII', total, len(info), len(info), flags) + data + info


class FastSplitTests(unittest.TestCase):
    def _write(self, payload):
        handle = tempfile.NamedTemporaryFile(delete=False)
        handle.write(payload)
        handle.close()
        self.addCleanup(os.unlink, handle.name)
        return handle.name

    def test_renames_cab_and_keeps_data(self):
        data = os.urandom(5000)
        src = self._write(_bundle([OLD], data))
        plan = fast_split.plan(src, NEW)
        out = io.BytesIO()
        plan.stream(out)
        result = out.getvalue()
        self.assertEqual(len(result), plan.length)
        size = struct.unpack('>q', result[len(result) - len(plan.tail) - len(data) - 20:][:8])[0]
        self.assertEqual(size, len(result))
        self.assertIn(data, result)
        self.assertIn(NEW.encode(), result)
        self.assertNotIn(OLD, result)

    def test_unsupported_layouts_fall_back(self):
        for payload in (_bundle([OLD, OLD + b'.resS']), _bundle([OLD], info_at_end=False),
                        _bundle([b'CAB-short'])):
            self.assertIsNone(fast_split.plan(self._write(payload), NEW))

    def test_pure_python_lz4_matches_known_block(self):
        # literal "abc" then match offset 3 length 6 -> "abcabcabc"
        block = bytes([0x32]) + b'abc' + bytes([3, 0])
        self.assertEqual(fast_split._lz4_decompress(block, 9)[:9], b'abcabcabc')


if __name__ == '__main__':
    unittest.main()
