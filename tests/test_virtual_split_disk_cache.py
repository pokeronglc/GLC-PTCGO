"""Virtual type-split bundles are built in a child process and served from disk.

Regression test for the VPS OOM kill: splits used to be rebuilt with UnityPy
inside the server and cached in RAM, which ratcheted memory up during a game.
"""
import hashlib
import os
import tempfile
import unittest
from unittest import mock

from spirit.server import http_server


class VirtualSplitDiskCacheTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = self.tmp.name
        self.src_dir = os.path.join(root, "en_US_SM5", "CAB-x")
        os.makedirs(self.src_dir)
        self.src = os.path.join(self.src_dir, "__data")
        # Non-Unity bytes: the worker falls back to plain CAB byte replacement.
        with open(self.src, "wb") as f:
            f.write(b"HEADER CAB-698f1293cb9396443b3f13ebe0cec855 BODY" * 10)
        self.cache_dir = os.path.join(root, "splits")
        patcher = mock.patch.object(http_server, "VIRTUAL_SPLIT_CACHE_DIR", self.cache_dir)
        patcher.start()
        self.addCleanup(patcher.stop)

    def tearDown(self):
        self.tmp.cleanup()

    def _handler(self):
        cls = next(v for v in vars(http_server).values()
                   if isinstance(v, type) and hasattr(v, "_virtual_split_path"))
        return object.__new__(cls)

    def test_split_is_built_on_disk_and_reused(self):
        handler = self._handler()
        filename = "en_US_SM5_fighting_625618534.unity3d"
        path = handler._virtual_split_path(filename, self.src, "SM5_fighting")
        self.assertIsNotNone(path)
        self.assertTrue(path.startswith(self.cache_dir))
        with open(path, "rb") as f:
            data = f.read()
        expected_cab = "CAB-" + hashlib.md5(b"SM5_fighting").hexdigest()
        self.assertIn(expected_cab.encode(), data)
        self.assertNotIn(b"CAB-698f1293cb9396443b3f13ebe0cec855", data)

        # Second request: served from the disk cache, no new build.
        with mock.patch("subprocess.run") as run:
            again = handler._virtual_split_path(filename, self.src, "SM5_fighting")
        run.assert_not_called()
        self.assertEqual(again, path)

    def test_changed_source_gets_a_new_cache_entry(self):
        filename = "en_US_SM5_fire_1.unity3d"
        first = http_server._virtual_split_cache_path(filename, self.src)
        with open(self.src, "ab") as f:
            f.write(b"more")
        self.assertNotEqual(first, http_server._virtual_split_cache_path(filename, self.src))

    def test_eviction_keeps_cache_within_budget(self):
        os.makedirs(self.cache_dir)
        for i in range(5):
            p = os.path.join(self.cache_dir, f"b{i}.unity3d")
            with open(p, "wb") as f:
                f.write(b"x" * 100)
            os.utime(p, (i, i))
        with mock.patch.object(http_server, "VIRTUAL_SPLIT_CACHE_MAX_BYTES", 250):
            http_server._evict_virtual_split_cache()
        self.assertEqual(sorted(os.listdir(self.cache_dir)), ["b3.unity3d", "b4.unity3d"])


if __name__ == "__main__":
    unittest.main()
