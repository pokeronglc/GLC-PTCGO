"""Matches show the Gym Leader Challenge card back instead of the Basic Sleeve."""
import os
import unittest
from unittest.mock import patch

from spirit.game import starter_content as sc


class GlcSleeveTests(unittest.TestCase):
    def test_basic_sleeve_becomes_glc(self):
        self.assertEqual(sc.match_sleeve(sc.STARTER_SLEEVE_GUID), sc.GLC_SLEEVE_GUID)
        self.assertEqual(sc.match_sleeve(sc.STARTER_SLEEVE_GUID.upper()), sc.GLC_SLEEVE_GUID)

    def test_other_sleeves_untouched_and_switch_off(self):
        other = "11111111-2222-3333-4444-555555555555"
        self.assertEqual(sc.match_sleeve(other), other)
        with patch.dict(os.environ, {"SPIRIT_GLC_SLEEVE": "0"}):
            self.assertEqual(sc.match_sleeve(sc.STARTER_SLEEVE_GUID), sc.STARTER_SLEEVE_GUID)

    def test_product_is_loaded(self):
        from spirit.game.scripts.products import loader
        products = loader.load_all()
        glc = [p for p in products if p.guid == sc.GLC_SLEEVE_GUID]
        self.assertEqual(len(glc), 1)
        self.assertEqual(glc[0].to_archetype_dict()["guid"], sc.GLC_SLEEVE_GUID)


if __name__ == "__main__":
    unittest.main()
