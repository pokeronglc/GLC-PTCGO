"""Gym Leader Challenge server: card pool and single-format configuration.

Builds its own GLC-filtered loader, so it also runs with SPIRIT_GLC_ONLY=0
(which the engine tests need, since they exercise the full card catalog).
"""
import collections
import unittest

from spirit.game import glc
from spirit.game.attributes import AttrID, DeckFormat
from spirit.game.data_utils import def_for
from spirit.game.format_manager import FormatManager, is_basic_energy_card
from spirit.game.scripts.cards import SCRIPTS_DIR, ScriptLoader
from spirit.game.starter_content import BOT_DECKS, parse_tcgo_decklist, SET_CODE_MAP

loader = ScriptLoader(SCRIPTS_DIR, glc_only=True)


def resolve_decklist(decklist):
    index = {(c.key.upper(), c.get_attribute_value(AttrID.COLLECTOR_NUMBER)): c.guid
             for c in loader.cards}
    guids = []
    for count, code, number in parse_tcgo_decklist(decklist):
        guid = index.get((SET_CODE_MAP.get(code.upper(), code).upper(), number))
        guids.extend([guid] * count)
    return guids


class GlcCardPoolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        loader.load_all()

    def test_no_loaded_card_is_outside_glc(self):
        offenders = [
            (def_for(c.guid).set_code, c.get_attribute_value(AttrID.COLLECTOR_NUMBER))
            for c in loader.cards if not glc.is_glc_legal(def_for(c.guid))
        ]
        self.assertEqual(offenders, [])

    def test_rule_box_ace_spec_and_old_sets_are_gone(self):
        for card in loader.cards:
            definition = def_for(card.guid)
            subtypes = set(definition.subtypes or [])
            self.assertNotIn(definition.set_code, glc.EXCLUDED_SETS)
            self.assertFalse(subtypes & glc.EXCLUDED_ANY_SUBTYPES, definition.display_name)
            if card.get_attribute_value(AttrID.CARD_TYPE) == 0:
                self.assertFalse(subtypes & glc.RULE_BOX_POKEMON_SUBTYPES, definition.display_name)

    def test_ban_list_is_applied(self):
        names = {def_for(c.guid).display_name for c in loader.cards}
        self.assertFalse(names & glc.BANNED_NAMES)
        prints = {(def_for(c.guid).set_code, c.get_attribute_value(AttrID.COLLECTOR_NUMBER))
                  for c in loader.cards}
        self.assertFalse(prints & glc.BANNED_PRINTS)

    def test_ordinary_cards_remain(self):
        names = {def_for(c.guid).display_name for c in loader.cards}
        for name in ("Professor's Research", "Rare Candy", "Psychic Energy", "Pikachu"):
            self.assertIn(name, names)


class GlcFormatTests(unittest.TestCase):
    def test_glc_rides_the_standard_slot(self):
        manager = FormatManager()
        self.assertEqual(manager.play_format_guids(),
                         [DeckFormat.STANDARD.value, DeckFormat.UNLIMITED.value])
        # The client hashes the wire name; Standard is "Modified" on the wire.
        self.assertEqual(manager.format_name(DeckFormat.STANDARD.value), "Modified")
        self.assertEqual(manager.resolve_format_guid("GymLeaderChallenge"),
                         DeckFormat.STANDARD.value)

    def test_standard_is_relabelled(self):
        from spirit.game.localization_overrides import relabel_archived_string, GLC_NAME
        self.assertEqual(relabel_archived_string("versusscreen.queuedropdown.standard",
                                                 "{standardqueue} Standard"),
                         "{standardqueue} " + GLC_NAME)
        self.assertEqual(relabel_archived_string("product.playmat.default.name",
                                                 "Standard Playmat"), "Standard Playmat")

    def test_bot_deck_is_glc_legal(self):
        loader.load_all()
        for name, decklist in BOT_DECKS:
            guids = resolve_decklist(decklist)
            self.assertEqual(len(guids), 60, name)
            cards = [loader.cards_by_guid[g] for g in guids]
            counts = collections.Counter(
                def_for(c.guid).display_name for c in cards if not is_basic_energy_card(c))
            self.assertEqual([n for n, k in counts.items() if k > 1], [], name)
            types = {c.get_attribute_value(AttrID.POKEMON_TYPES)
                     for c in cards if c.get_attribute_value(AttrID.CARD_TYPE) == 0}
            self.assertEqual(len(types), 1, name)



class GlcDeckRuleTests(unittest.TestCase):
    """Singleton and one-type rules, run against the GLC-filtered catalog."""

    @classmethod
    def setUpClass(cls):
        loader.load_all()
        cls.bot = resolve_decklist(BOT_DECKS[0][1])
        cls.by_name = {}
        for card in loader.cards:
            cls.by_name.setdefault(def_for(card.guid).display_name, card)

    def failures(self, guids):
        from spirit.game.rules import card_display_name
        cards = [loader.cards_by_guid[g] for g in guids]
        return glc.deck_rule_failures(cards, card_display_name, is_basic_energy_card)

    def swap(self, old_name, new_card):
        guids = list(self.bot)
        for i, g in enumerate(guids):
            if def_for(g).display_name == old_name:
                guids[i] = new_card.guid
                return guids
        raise AssertionError(old_name)

    def test_bot_deck_passes(self):
        self.assertEqual(self.failures(self.bot), [])

    def test_two_copies_fail(self):
        guids = self.swap("Iono", loader.cards_by_guid[next(
            g for g in self.bot if def_for(g).display_name == "Arven")])
        kinds = [f[0] for f in self.failures(guids)]
        self.assertIn("MaxDuplicates", kinds)

    def test_name_variants_count_as_one_name(self):
        self.assertEqual(glc.singleton_name("Professor's Research (Professor Turo)"),
                         "Professor's Research")
        self.assertEqual(glc.singleton_name("Lysandre"), "Boss's Orders")

    def test_second_type_fails(self):
        fire = next(c for c in loader.cards
                    if c.get_attribute_value(AttrID.CARD_TYPE) == 0
                    and c.get_attribute_value(AttrID.POKEMON_TYPES) in ("[6]", [6]))
        guids = self.swap("Gengar", fire)
        failures = self.failures(guids)
        self.assertEqual([f[0] for f in failures], ["MustNotContain"])
        self.assertEqual(failures[0][2], [fire.guid.lower()])


if __name__ == "__main__":
    unittest.main()
