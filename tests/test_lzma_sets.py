import os
import tempfile
import time
import unittest
from unittest.mock import patch

from spirit.server import lzma_sets as lz


class LzmaSetsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.src_dir = os.path.join(self.tmp.name, "bundleCache", "en_US_SM11", "0000")
        os.makedirs(self.src_dir)
        self.src = os.path.join(self.src_dir, "__data")
        with open(self.src, "wb") as fh:
            fh.write(b"x" * 100)
        self.out = os.path.join(self.tmp.name, "lzma_sets")

    def tearDown(self):
        self.tmp.cleanup()

    def test_off_by_default(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("SPIRIT_LZMA_SETS", None)
            self.assertFalse(lz.enabled())
        with patch.dict(os.environ, {"SPIRIT_LZMA_SETS": "1"}):
            self.assertTrue(lz.enabled())

    def test_names_and_dir(self):
        self.assertEqual(lz.set_name(self.src), "SM11")
        self.assertTrue(os.path.basename(lz.copy_path(self.out, self.src)).startswith("lzma-SM11-"))
        os.environ.pop("SPIRIT_LZMA_DIR", None)
        self.assertEqual(lz.cache_dir("/mnt/vol/splitcache"), "/mnt/vol/lzma_sets")

    def test_existing_copy_only_when_built_and_fresh(self):
        self.assertIsNone(lz.existing_copy(self.out, self.src))
        path = lz.copy_path(self.out, self.src)
        os.makedirs(self.out)
        open(path, "wb").close()
        self.assertEqual(lz.existing_copy(self.out, self.src), path)
        # source bundle changes -> old copy is ignored
        time.sleep(0.01)
        with open(self.src, "ab") as fh:
            fh.write(b"more")
        self.assertIsNone(lz.existing_copy(self.out, self.src))

    def test_missing_source_is_safe(self):
        self.assertIsNone(lz.existing_copy(self.out, os.path.join(self.tmp.name, "nope")))


if __name__ == "__main__":
    unittest.main()
