"""Slim per-type split bundles: which cards go in which type file, and the
worker that cuts a set bundle down to them."""
import json
import os
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

from spirit.game.attributes import CardType, PokemonTypes
from spirit.server import typed_splits as ts


class SuffixRuleTests(unittest.TestCase):
    def test_pokemon_types(self):
        self.assertEqual(ts.suffixes_for(CardType.POKEMON.value, [PokemonTypes.WATER.value]), {"water"})
        self.assertEqual(ts.suffixes_for(CardType.POKEMON.value,
                                         [PokemonTypes.FIRE.value, PokemonTypes.DRAGON.value]),
                         {"fire", "dragon"})
        self.assertEqual(ts.suffixes_for(CardType.POKEMON.value, None), ts.ALL_SUFFIXES)

    def test_trainers_energy(self):
        self.assertEqual(ts.suffixes_for(CardType.TRAINER.value, None), {"trainer"})
        self.assertEqual(ts.suffixes_for(CardType.TRAINER.value, [1], plays_as_pokemon=True),
                         {"trainer", "colorless"})
        self.assertEqual(ts.suffixes_for(CardType.ENERGY.value, [PokemonTypes.GRASS.value]), {"grass"})
        self.assertEqual(ts.suffixes_for(CardType.ENERGY.value, [PokemonTypes.GRASS.value],
                                         special_energy=True), ts.ALL_SUFFIXES)

    def test_new_revision_gives_new_identity(self):
        import zlib
        with patch.dict(os.environ, {"SPIRIT_TYPED_SPLITS": "1"}):
            self.assertEqual(ts.manifest_version(5, "SV4_water"),
                             zlib.crc32(f"5:typed{ts.REVISION}:SV4_water".encode()) & 0x7FFFFFFF)
            self.assertNotEqual(ts.manifest_version(5, "SV4_water"),
                                zlib.crc32(b"5:typed:SV4_water") & 0x7FFFFFFF)

    def test_no_experiment_left(self):
        self.assertFalse(hasattr(ts, "EXPERIMENT"))

    def test_split_parts(self):
        self.assertEqual(ts.split_parts("SV4_water"), ("SV4", "water"))
        self.assertEqual(ts.split_parts("SWSH12pt5_trainer"), ("SWSH12pt5", "trainer"))
        self.assertIsNone(ts.split_parts("SV4"))
        self.assertIsNone(ts.split_parts("Free_Energy"))

    def test_manifest_version_only_changes_when_enabled(self):
        with patch.dict(os.environ, {"SPIRIT_TYPED_SPLITS": "0"}):
            self.assertEqual(ts.manifest_version(123, "SV4_water"), 123)
        with patch.dict(os.environ, {"SPIRIT_TYPED_SPLITS": "1"}):
            a = ts.manifest_version(123, "SV4_water")
            self.assertNotEqual(a, 123)
            self.assertNotEqual(a, ts.manifest_version(123, "SV4_fire"))
            self.assertGreater(a, 0)


class DropNameTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        ts._INDEX = None

    def test_real_set_partition(self):
        from spirit.game.scripts.cards import loader
        from spirit.game.data_utils import def_for
        from spirit.game.attributes import AttrID
        drop_water = ts.drop_names("SV4", "water")
        drop_trainer = ts.drop_names("SV4", "trainer")
        self.assertIsNotNone(drop_water)
        names = {}
        for model in loader.cards:
            d = def_for(model.guid)
            if d is not None and d.set_code == "SV4":
                names[d.display_name] = model.get_attribute_value(AttrID.IMAGE_URL)
        self.assertNotIn(names["Wimpod"], drop_water)          # Water Pokémon kept
        self.assertIn(names["Wimpod"], drop_trainer)
        self.assertNotIn(names["Shauntal"], drop_trainer)      # Supporter kept in trainer
        self.assertIn(names["Shauntal"], drop_water)
        self.assertNotIn(names["Reversal Energy"], drop_water)  # Special Energy everywhere
        self.assertNotIn(names["Reversal Energy"], drop_trainer)
        self.assertNotIn(names["Snorlax Doll"], ts.drop_names("SV4", "colorless"))
        # every card is in at least one type file
        kept = set()
        for suffix in ts.ALL_SUFFIXES:
            kept |= set(names.values()) - ts.drop_names("SV4", suffix)
        self.assertEqual(kept, set(names.values()))

    def test_unknown_set(self):
        self.assertIsNone(ts.drop_names("NOPE", "water"))
        self.assertIsNone(ts.drop_names("SV4", "energy"))


class WorkerTests(unittest.TestCase):
    """Runs the worker against a fake UnityPy environment."""

    def test_drops_named_textures_and_container_entries(self):
        sys.path.insert(0, os.path.dirname(ts.WORKER_SCRIPT))
        import typed_split_worker as worker

        def obj(type_name, name=None):
            o = types.SimpleNamespace(type=types.SimpleNamespace(name=type_name))
            o.peek_name = lambda: name
            return o

        def info(pid):
            return types.SimpleNamespace(asset=types.SimpleNamespace(m_PathID=pid))

        bundle = types.SimpleNamespace(m_Container=[("001", info(1)), ("SV4/001", info(1)),
                                                     ("002", info(2)), ("shader", info(9))],
                                       m_PreloadTable=[])
        ab = obj("AssetBundle")
        ab.read = lambda: bundle
        saved = {}
        ab.save_typetree = lambda data: saved.setdefault("bundle", data)
        objects = {1: obj("Texture2D", "001"), 2: obj("Texture2D", "002"),
                   9: obj("Shader", "s"), 10: ab, 11: obj("Texture2D", "template")}
        asset = types.SimpleNamespace(objects=objects, name="CAB-old")
        env = types.SimpleNamespace(assets=[asset],
                                    file=types.SimpleNamespace(files={"CAB-old": asset},
                                                               save=lambda packer: b"BUNDLE"))
        fake = types.SimpleNamespace(load=lambda data: env)
        with tempfile.TemporaryDirectory() as tmp, patch.dict(sys.modules, {"UnityPy": fake}):
            src = os.path.join(tmp, "src")
            with open(src, "wb") as handle:
                handle.write(b"x")
            out = os.path.join(tmp, "out.unity3d")
            worker.build(src, out, "CAB-new", {"002"})
            with open(out, "rb") as handle:
                self.assertEqual(handle.read(), b"BUNDLE")
        self.assertNotIn(2, objects)
        self.assertIn(1, objects)
        self.assertIn(11, objects)
        self.assertEqual([n for n, _ in bundle.m_Container], ["001", "SV4/001", "shader"])
        self.assertIn("CAB-new", env.file.files)
        self.assertEqual(asset.name, "CAB-new")


class TextureOnlyWorkerTests(unittest.TestCase):
    """Texture-only bundles: dropped cards AND template leftovers go, and the
    preload table is rebuilt to match the container."""

    def test_template_leftovers_removed(self):
        sys.path.insert(0, os.path.dirname(ts.WORKER_SCRIPT))
        import typed_split_worker as worker

        def tex(pid, name):
            o = types.SimpleNamespace(type=types.SimpleNamespace(name="Texture2D"), path_id=pid)
            o.peek_name = lambda: name
            o.read = lambda: types.SimpleNamespace(m_Name=name, m_StreamData=None)
            return o

        def info(pid):
            return types.SimpleNamespace(asset=types.SimpleNamespace(m_PathID=pid),
                                         preloadIndex=0, preloadSize=0)

        bundle = types.SimpleNamespace(m_Container=[("001", info(1)), ("SV4/001", info(1)),
                                                     ("002", info(2))],
                                       m_PreloadTable=["stale"], m_MainAsset=None)
        ab = types.SimpleNamespace(type=types.SimpleNamespace(name="AssetBundle"), path_id=10)
        ab.read = lambda: bundle
        ab.save_typetree = lambda data: None
        objects = {1: tex(1, "001"), 2: tex(2, "002"), 11: tex(11, "template"), 10: ab}
        asset = types.SimpleNamespace(objects=objects, name="CAB-old", externals=[])

        class Env:
            assets = [asset]
            file = types.SimpleNamespace(files={"CAB-old": asset}, save=lambda packer: b"BUNDLE")

            @property
            def objects(self):
                return list(asset.objects.values())
        env = Env()
        fake = types.SimpleNamespace(load=lambda data: env)
        with tempfile.TemporaryDirectory() as tmp, patch.dict(sys.modules, {"UnityPy": fake}):
            src = os.path.join(tmp, "src")
            with open(src, "wb") as handle:
                handle.write(b"x")
            worker.build(src, os.path.join(tmp, "out.unity3d"), "CAB-new", {"002"})
        self.assertEqual(sorted(objects), [1, 10])            # 002 and template gone
        self.assertEqual([n for n, _ in bundle.m_Container], ["001", "SV4/001"])
        self.assertEqual(len(bundle.m_PreloadTable), 2)
        self.assertEqual([i.preloadIndex for _, i in bundle.m_Container], [0, 1])


class RoutingTests(unittest.TestCase):
    def test_asset_number(self):
        self.assertEqual(ts.asset_number("094", "SM11"), 94)
        self.assertEqual(ts.asset_number("SM11/94", "SM11"), 94)
        self.assertEqual(ts.asset_number("SM11_foil_094", "SM11"), 94)
        self.assertEqual(ts.asset_number("094_toolpip", "SM11"), 94)
        self.assertIsNone(ts.asset_number("en_US_SM11", "SM11"))
        self.assertIsNone(ts.asset_number("SM11_water", "SM11"))

    def test_route_kind(self):
        self.assertEqual(ts.route_kind({"trainer"}), "trainer")
        self.assertEqual(ts.route_kind({"trainer", "colorless"}), "trainer")
        self.assertEqual(ts.route_kind(ts.ALL_SUFFIXES), "trainer")
        self.assertEqual(ts.route_kind({"water", "fairy"}), "fairy")

    def test_real_routes_point_at_files_that_hold_the_card(self):
        routes = ts.card_routes("SM11")
        self.assertEqual(routes[211], "trainer")             # U-Turn Board
        for number, kind in routes.items():
            drop = ts.drop_names("SM11", kind)
            self.assertNotIn(f"{number:03d}", drop, f"{number} not in SM11_{kind}")

    def test_switch(self):
        with patch.dict(os.environ, {"SPIRIT_ROUTE_CARDS": "0"}):
            self.assertFalse(ts.routing_enabled("SM11"))
        with patch.dict(os.environ, {"SPIRIT_ROUTE_CARDS": "1"}):
            self.assertTrue(ts.routing_enabled("SV4"))
        with patch.dict(os.environ, {"SPIRIT_ROUTE_CARDS": "SM11, me2"}):
            self.assertTrue(ts.routing_enabled("SM11"))
            self.assertTrue(ts.routing_enabled("ME2"))
            self.assertFalse(ts.routing_enabled("SV4"))

    def test_manifest_moves_card_assets_to_type_files(self):
        from spirit.server.manifest_manager import ManifestManager
        web = "en_US/en_US_SM11.unity3d"
        whole = {"name": "SM11", "WebPath": web, "assets": [
            {"name": "211"}, {"name": "SM11/211"}, {"name": "SM11_211_toolpip"},
            {"name": "en_US_SM11"}, {"name": "SM11"}]}
        descriptors = {"SM11": whole}
        for k in ts.ALL_SUFFIXES:
            descriptors[f"SM11_{k}"] = {"name": f"SM11_{k}", "WebPath": web,
                                        "assets": [{"name": f"SM11_{k}"}]}
        ManifestManager._route_card_assets(whole, "SM11", descriptors)
        self.assertEqual([a["name"] for a in whole["assets"]], ["en_US_SM11", "SM11"])
        self.assertEqual([a["name"] for a in descriptors["SM11_trainer"]["assets"]],
                         ["SM11_trainer", "211", "SM11/211", "SM11_211_toolpip"])


class ServePathTests(unittest.TestCase):
    def test_built_once_then_served_from_cache(self):
        import spirit.server.http_server as http
        calls = []

        def fake_build(src, out, clean_base, drop, timeout=0):
            calls.append(clean_base)
            os.makedirs(os.path.dirname(out), exist_ok=True)
            with open(out, "wb") as handle:
                handle.write(b"slim")
            return True

        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "__data")
            with open(src, "wb") as handle:
                handle.write(b"x")
            with patch.object(http, "VIRTUAL_SPLIT_CACHE_DIR", os.path.join(tmp, "cache")), \
                 patch.object(ts, "build", fake_build):
                path = http.MockHTTPRequestHandler._typed_split_path(None, "f", src, "SV4_water")
                again = http.MockHTTPRequestHandler._typed_split_path(None, "f", src, "SV4_water")
                self.assertEqual(path, again)
                self.assertEqual(calls, ["SV4_water"])
                self.assertIsNone(http.MockHTTPRequestHandler._typed_split_path(None, "f", src, "SV4"))
                self.assertIsNone(http.MockHTTPRequestHandler._typed_split_path(None, "f", src, "NOPE_water"))


if __name__ == "__main__":
    unittest.main()
