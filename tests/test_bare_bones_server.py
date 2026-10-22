"""Bare-bones server: no coins/packs/shop, blank avatars."""
import asyncio
import os
import tempfile
import unittest
from unittest.mock import AsyncMock, MagicMock

from tests import test_hgss_rules as fixtures


class BareBonesTests(unittest.TestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)

    def test_strip_economy_zeroes_wallet_and_removes_packs(self):
        from contextlib import contextmanager
        from types import SimpleNamespace
        from unittest.mock import patch
        from spirit.database import player_data
        from spirit.game.attributes import ProductType
        from spirit.game.scripts.products import loader as product_loader
        product_loader.load_all()
        pack = next(p for p in product_loader.products
                    if p.product_type == ProductType.PACKS.value)
        wallet = SimpleNamespace(coins=500, gems=3, tickets=7)
        rows = [SimpleNamespace(archetype_id=pack.guid.upper()),
                SimpleNamespace(archetype_id='some-card')]

        class Query:
            def __init__(self, model):
                self.model = model
            def filter_by(self, **kw):
                return self
            def first(self):
                return wallet
            def all(self):
                return list(rows)

        class FakeSession:
            def query(self, model):
                return Query(model)
            def delete(self, row):
                rows.remove(row)

        @contextmanager
        def fake_db():
            yield FakeSession()

        with patch.object(player_data, 'db_session', fake_db):
            self.assertTrue(player_data.strip_economy('a1'))
        self.assertEqual((wallet.coins, wallet.gems, wallet.tickets), (0, 0, 0))
        self.assertEqual([r.archetype_id for r in rows], ['some-card'])

    def test_shop_features_are_not_offered(self):
        from spirit.packets.handlers.data_sync import DataSyncHandler
        from spirit.game.attributes import FeatureToken
        client = MagicMock()
        client.send_packet = AsyncMock()
        handler = DataSyncHandler(client)
        asyncio.run(handler.handle_get_feature_statuses_v2({}, 1, 0))
        sent = client.send_packet.await_args.args[0]
        names = {f['featureName'] for f in sent['open']}
        for gone in (FeatureToken.COMMERCE_FEATURE, FeatureToken.STORE_GENERIC_FEATURE,
                     FeatureToken.EXCHANGE_FEATURE, FeatureToken.CODES_ENABLED,
                     FeatureToken.DRAFT_FEATURE):
            self.assertNotIn(gone, names)
        self.assertIn(FeatureToken.DECK_BUILDER_FEATURE, names)

    def test_avatar_catalogue_is_blank(self):
        from spirit.game.models import avatar
        avatar._AVATAR_ITEMS_CACHE = None
        self.assertEqual(avatar.get_avatar_items(), {})
        defaults = avatar.get_default_avatar_items_list()
        self.assertEqual(len(defaults), 16)
        self.assertTrue(all(g.startswith('00000000-0000-0000-0000-000000000a') for g in defaults))

    def test_singleton_collection_on_login(self):
        from contextlib import contextmanager
        from types import SimpleNamespace
        from unittest.mock import patch
        from spirit.database import player_data
        from spirit.game.scripts.cards import loader
        from spirit.game.format_manager import is_basic_energy_card
        cards = loader.load_all()
        regular = next(c for c in cards if not is_basic_energy_card(c))
        energy = next(c for c in cards if is_basic_energy_card(c))
        rows = {regular.guid: SimpleNamespace(archetype_id=regular.guid,
                                              tradable_count=4, nontradable_count=2)}

        class Query:
            def filter_by(self, **kw):
                return self
            def all(self):
                return list(rows.values())

        class FakeSession:
            def query(self, model):
                return Query()
            def add(self, row):
                rows[row.archetype_id] = row

        @contextmanager
        def fake_db():
            yield FakeSession()

        with patch.object(player_data, 'db_session', fake_db), \
                patch.object(player_data, 'Collection',
                             lambda **kw: SimpleNamespace(**kw)):
            player_data.grant_all_cards('a1', count=1, is_tradable=True, exact=True)
        self.assertEqual((rows[regular.guid].tradable_count, rows[regular.guid].nontradable_count), (1, 0))
        self.assertGreater(rows[energy.guid].tradable_count, 1)


if __name__ == "__main__":
    unittest.main()
