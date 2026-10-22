"""Bug hunt, deck 7 (Water): Supporters, Items, Stadium and Special Energy."""
import unittest
from unittest.mock import patch

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table
from spirit.game.attributes import AttrID, PokemonTypes
from spirit.game.data_utils import def_for
from spirit.tools.effect_smoke import P1, P2

W, L, F = PokemonTypes.WATER, PokemonTypes.LIGHTNING, PokemonTypes.FIRE
FRIGIBAX, ARCTIBAX = 'SV045.Frigibax_17', 'SV2.Arctibax_59'
SNOM, FROSMOTH, SOBBLE, DRIZZILE = 'SV05.Snom_45', 'SWSH1.Frosmoth_64', 'SWSH1.Sobble_55', 'SWSH1.Drizzile_56'
WAILORD, KYOGRE, BLITZLE, ZEBSTRIKA = 'SV09.Wailord_41', 'CZ.Kyogre_36', 'SV08.Blitzle_62', 'SM8.Zebstrika_82'
AREZU, GLADION, IRIDA, NESSA = 'SWSH11.Arezu_153', 'SM4.Gladion_95', 'SWSH10.Irida_147', 'SWSH4.Nessa_157'
BUCKET, DIVE, VESSEL = 'SWSH2.CapaciousBucket_156', 'XY5.DiveBall_125', 'SV4.EarthenVessel_163'
HAUL_NET, SER = 'ME4.GreatHaulNet_78', 'SV2.SuperiorEnergyRetrieval_189'
ROUGH_SEAS = 'XY5.RoughSeas_137'
REVERSAL, SPLASH = 'SV2.ReversalEnergy_192', 'XY9.SplashEnergy_113'
NEST, FLOAT = 'SV1.NestBall_181', 'XY8.FloatStone_137'
FILLER_NAME = 'Pokégear 3.0'


class Deck7Trainers(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    def table(self, active=None):
        t = Table(self)
        self.me = t.put(active or self.filler, P1, 'active')
        self.opp = t.put(self.filler, P2, 'active')
        for attr in (AttrID.WEAKNESS_TYPES, AttrID.RESISTANCE_TYPES):
            self.opp.set_attribute(attr, [])
        self.opp.set_attribute(AttrID.HP, 400)
        return t

    def name(self, card):
        return def_for(card.archetype_id).display_name

    def hand_names(self, t, pid=P1):
        return t.names(t.zone(pid, 'hand'))

    def recording_picks(self, t, seen, prefer=lambda c: True):
        def picks(cards, count, prompt, display):
            seen.append((t.names(cards), count))
            good = [c for c in cards if self.name(c) != FILLER_NAME and prefer(c)]
            return (good + [c for c in cards if c not in good])[:count]
        return picks

    # --- Arezu ---------------------------------------------------------
    async def test_arezu_up_to_three_evolution_pokemon(self):
        t = self.table()
        t.deck(P1, [ARCTIBAX, FROSMOTH, DRIZZILE, ZEBSTRIKA, SNOM, SOBBLE])
        seen = []
        t.picks = self.recording_picks(t, seen)
        await t.play(t.put(AREZU, P1, 'hand'))
        names, count = seen[0]
        self.assertEqual(count, 3)
        self.assertNotIn('Snom', names)
        self.assertNotIn('Sobble', names)
        self.assertEqual(len(t.zone(P1, 'hand')), 3)

    # --- Gladion ----------------------------------------------------------
    async def test_gladion_swaps_with_a_prize(self):
        t = self.table()
        prize = t.zone(P1, 'prizes')[0]
        t.board.find_player_area(P1, 'prizePile').remove_child(prize)
        target = t.put(NESSA, P1, 'prizes')
        gladion = t.put(GLADION, P1, 'hand')
        offered = {}

        async def prize_pick(pid, source_id, prize_ids, pickable_ids, prompt=None, forced=False):
            offered['ids'] = list(pickable_ids)
            return target.entity_id
        with patch.object(t.session, 'prompt_prize_reveal_pick', prize_pick):
            await t.play(gladion)
        self.assertEqual(len(offered['ids']), 6)            # any Prize may be taken
        self.assertIn(target, t.zone(P1, 'hand'))
        self.assertIn(gladion, t.zone(P1, 'prizes'))
        self.assertEqual(len(t.zone(P1, 'prizes')), 6)
        self.assertNotIn(gladion, t.zone(P1, 'discard'))

    # --- Irida -----------------------------------------------------------
    async def test_irida_water_pokemon_and_item(self):
        t = self.table()
        t.deck(P1, [BLITZLE, FLOAT, SNOM, NEST])
        seen = []

        async def groups(pid, source_id, specs, prompt, display_cards=None, total=None, any_of=False):
            out = []
            for spec in specs:
                seen.append(t.names(spec['cards']))
                good = [c for c in spec['cards'] if self.name(c) != FILLER_NAME]
                out.append([c.entity_id for c in (good + list(spec['cards']))[:spec['count']]])
            return out
        with patch.object(t.session, 'prompt_card_chooser_groups', groups):
            await t.play(t.put(IRIDA, P1, 'hand'))
        self.assertEqual(self.hand_names(t), ['Nest Ball', 'Snom'])
        self.assertNotIn('Blitzle', seen[0])
        self.assertNotIn('Float Stone', seen[1])

    # --- Nessa ---------------------------------------------------------
    async def test_nessa_water_pokemon_and_water_energy(self):
        t = self.table()
        for spec in (SNOM, SOBBLE, BLITZLE, t.basic_energy(W), t.basic_energy(W), t.basic_energy(F)):
            t.put(spec, P1, 'discard')
        seen = []
        t.picks = self.recording_picks(t, seen)
        await t.play(t.put(NESSA, P1, 'hand'))
        names, count = seen[0]
        self.assertEqual(count, 4)
        self.assertNotIn('Blitzle', names)
        self.assertEqual(len(t.zone(P1, 'hand')), 4)
        self.assertEqual(len([c for c in t.zone(P1, 'discard') if self.name(c) != 'Nessa']), 2)

    async def test_nessa_needs_water_cards_in_discard(self):
        t = self.table()
        t.put(BLITZLE, P1, 'discard')
        t.put(t.basic_energy(F), P1, 'discard')
        card = t.put(NESSA, P1, 'hand')
        self.assertFalse(t.can(card, 'UseTrainerCard'))

    # --- Capacious Bucket ------------------------------------------------
    async def test_capacious_bucket_basic_water_only(self):
        t = self.table()
        t.deck(P1, [t.basic_energy(W), t.basic_energy(W), t.basic_energy(W), SPLASH, t.basic_energy(F)])
        seen = []
        t.picks = self.recording_picks(t, seen)
        await t.play(t.put(BUCKET, P1, 'hand'))
        names, count = seen[0]
        self.assertEqual(count, 2)
        self.assertNotIn('Splash Energy', names)
        hand = t.zone(P1, 'hand')
        self.assertEqual(len(hand), 2)
        self.assertTrue(all(c.archetype_id.lower() == t.basic_energy(W).guid.lower() for c in hand))

    # --- Dive Ball -----------------------------------------------------
    async def test_dive_ball_water_pokemon_only(self):
        t = self.table()
        t.deck(P1, [BLITZLE, SNOM])
        seen = []
        t.picks = self.recording_picks(t, seen)
        await t.play(t.put(DIVE, P1, 'hand'))
        self.assertEqual(self.hand_names(t), ['Snom'])
        self.assertNotIn('Blitzle', seen[0][0])

    # --- Earthen Vessel ---------------------------------------------------
    async def test_earthen_vessel_discard_one_two_basic_energy(self):
        t = self.table()
        t.deck(P1, [t.basic_energy(W), t.basic_energy(L), t.basic_energy(F), SPLASH])
        junk = t.put(NEST, P1, 'hand')
        seen = []

        def picks(cards, count, prompt, display):
            seen.append((t.names(cards), count, prompt))
            if junk in cards:
                return [junk]
            good = [c for c in cards if self.name(c) != FILLER_NAME]
            return good[:count]
        t.picks = picks
        await t.play(t.put(VESSEL, P1, 'hand'))
        self.assertIn(junk, t.zone(P1, 'discard'))
        hand = t.zone(P1, 'hand')
        self.assertEqual(len(hand), 2)
        self.assertNotIn('Splash Energy', t.names(hand))
        self.assertTrue(all('Splash Energy' not in s[0] for s in seen if junk not in []))

    async def test_earthen_vessel_needs_another_card(self):
        t = self.table()
        t.deck(P1, [t.basic_energy(W)])
        vessel = t.put(VESSEL, P1, 'hand')
        self.assertFalse(t.can(vessel, 'UseTrainerCard'))

    # --- Great Haul Net ---------------------------------------------------
    async def test_great_haul_net_water_pokemon_and_basic_water(self):
        t = self.table()
        for spec in (SNOM, SOBBLE, KYOGRE, WAILORD, BLITZLE):
            t.put(spec, P1, 'discard')
        for _ in range(4):
            t.put(t.basic_energy(W), P1, 'discard')
        t.put(SPLASH, P1, 'discard')
        seen = []
        t.picks = self.recording_picks(t, seen)
        deck = len(t.zone(P1, 'deck'))
        from unittest.mock import patch
        from spirit.game.session.effects import EffectContext

        async def both(ctx, prompt, buttons, *a, **k):
            return buttons.index('Both')
        with patch.object(EffectContext, 'choose', both):
            await t.play(t.put(HAUL_NET, P1, 'hand'))
        self.assertEqual(len(t.zone(P1, 'deck')), deck + 6)
        self.assertTrue(all(count == 3 for _, count in seen))
        for names, _ in seen:
            self.assertNotIn('Blitzle', names)
            self.assertNotIn('Splash Energy', names)

    async def test_great_haul_net_needs_water_cards(self):
        t = self.table()
        t.put(BLITZLE, P1, 'discard')
        t.put(SPLASH, P1, 'discard')
        net = t.put(HAUL_NET, P1, 'hand')
        self.assertFalse(t.can(net, 'UseTrainerCard'))

    # --- Superior Energy Retrieval ----------------------------------------
    async def test_superior_energy_retrieval_discard_two_get_four_basic(self):
        t = self.table()
        for _ in range(5):
            t.put(t.basic_energy(W), P1, 'discard')
        t.put(SPLASH, P1, 'discard')
        a, b = t.put(NEST, P1, 'hand'), t.put(FLOAT, P1, 'hand')
        seen = []

        def picks(cards, count, prompt, display):
            seen.append((t.names(cards), count))
            if a in cards:
                return [a, b][:count]
            return cards[:count]
        t.picks = picks
        await t.play(t.put(SER, P1, 'hand'))
        hand = t.zone(P1, 'hand')
        self.assertEqual(len(hand), 4)
        self.assertNotIn('Splash Energy', t.names(hand))
        self.assertIn(a, t.zone(P1, 'discard'))
        self.assertIn(b, t.zone(P1, 'discard'))

    async def test_superior_energy_retrieval_needs_two_other_cards(self):
        t = self.table()
        t.put(t.basic_energy(W), P1, 'discard')
        t.put(NEST, P1, 'hand')
        card = t.put(SER, P1, 'hand')
        self.assertFalse(t.can(card, 'UseTrainerCard'))

    # --- Rough Seas -------------------------------------------------------
    async def test_rough_seas_heals_water_and_lightning_once_per_player(self):
        t = Table(self)
        water = t.put(SNOM, P1, 'active', hp=10)          # 50 HP, 40 damage
        light = t.put(ZEBSTRIKA, P1, 'bench', hp=50)       # 110 HP, 60 damage
        other = t.put(self.filler, P1, 'bench')
        other.set_attribute(AttrID.HP, t.hp(other) - 50)
        opp_water = t.put(SOBBLE, P2, 'active', hp=20)     # 70 HP, 50 damage
        seas = t.stadium(ROUGH_SEAS, P2)                    # either player's Stadium
        entry = next(iter(t.offers(seas, None, P1)), None)
        self.assertIsNotNone(entry)
        await t.do(entry)
        self.assertEqual(t.damage(water), 10)
        self.assertEqual(t.damage(light), 30)
        self.assertEqual(t.damage(other), 50)              # Colorless isn't healed
        self.assertEqual(t.damage(opp_water), 50)          # only the user's side
        self.assertIsNone(next(iter(t.offers(seas, None, P1)), None))
        t.next_turn()
        entry = next(iter(t.offers(seas, None, P2)), None)
        self.assertIsNotNone(entry)
        await t.do(entry, pid=P2)
        self.assertEqual(t.damage(opp_water), 20)

    # --- Reversal Energy ---------------------------------------------------
    async def test_reversal_energy_every_type_on_evolution_when_behind(self):
        for mine, theirs, offered in ((4, 3, True), (3, 3, False)):
            t = self.table(ARCTIBAX)             # Frost Smash: [W][W][C]
            t.attach(REVERSAL, self.me)
            t.set_prizes(P1, mine); t.set_prizes(P2, theirs)
            with self.subTest(mine=mine, theirs=theirs):
                self.assertEqual(t.attack_offer(self.me, 'Frost Smash') is not None, offered)

    async def test_reversal_energy_colorless_on_basic(self):
        t = self.table(FRIGIBAX)                 # Collect: [W]; Pound-like [C] none
        t.attach(REVERSAL, self.me)
        t.set_prizes(P1, 5); t.set_prizes(P2, 2)
        self.assertIsNone(t.attack_offer(self.me, 'Collect'))
        t = self.table(BLITZLE)                  # Add On: [C]
        t.attach(REVERSAL, self.me)
        self.assertIsNotNone(t.attack_offer(self.me, 'Add On'))

    # --- Splash Energy ---------------------------------------------------
    async def test_splash_energy_only_attaches_to_water(self):
        t = self.table(SNOM)
        splash = t.put(SPLASH, P1, 'hand')
        blitzle = t.put(BLITZLE, P1, 'bench')
        targets = t.targets(splash, 'DefaultEnergyPlayAbility')
        self.assertIn(self.me.entity_id, targets)
        self.assertNotIn(blitzle.entity_id, targets)

    async def test_splash_energy_returns_knocked_out_water_pokemon(self):
        t = Table(self)
        snom = t.put(SNOM, P1, 'active', hp=10)
        snom.set_attribute(AttrID.WEAKNESS_TYPES, [])
        splash = t.attach(SPLASH, snom)
        basic = t.energy(snom, W)
        t.put(self.filler, P1, 'bench')
        attacker = t.put(BLITZLE, P2, 'active')
        t.energy(attacker, L, 2)
        t.next_turn()
        await t.attack(attacker, 'Static Shock', pid=P2)
        self.assertIn(snom, t.zone(P1, 'hand'))
        self.assertIn(splash, t.zone(P1, 'discard'))
        self.assertIn(basic, t.zone(P1, 'discard'))

    async def test_splash_energy_not_on_poison_knockout(self):
        t = Table(self)
        t.put(self.filler, P2, 'active')
        snom = t.put(SNOM, P1, 'active', hp=10)
        t.attach(SPLASH, snom)
        t.put(self.filler, P1, 'bench')
        snom.set_attribute(AttrID.SPECIAL_CONDITIONS, ['Poisoned'])
        await t.checkup()
        self.assertNotIn(snom, t.zone(P1, 'hand'))
        self.assertIn(snom, t.zone(P1, 'discard'))
    # Was a bug (fixed Oct 10): Energy that provides nothing (Splash on a non-Water Pokemon) still pays [C] in attack costs.
    async def test_splash_energy_on_non_water_provides_nothing(self):
        t = self.table(BLITZLE)                  # Add On: [C]
        t.attach(SPLASH, self.me)                # moved there by an effect
        self.assertIsNone(t.attack_offer(self.me, 'Add On'))

    async def test_splash_energy_on_non_water_is_discarded(self):
        from spirit.game.session.effects import EffectContext
        t = self.table(BLITZLE)
        splash = t.attach(SPLASH, self.me)
        ctx = EffectContext(t.session, P1, self.me, None)
        await t._run(lambda: ctx.enforce_attachment_restrictions(self.me))
        self.assertIn(splash, t.zone(P1, 'discard'))


if __name__ == "__main__":
    unittest.main()
