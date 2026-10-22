"""Bug hunt round 7, chunk 8: Academy at Night, Trubbish x2, Drampa, Brock's
Scouting, Dragonium Z: Dragon Claw, Marshtomp, Pelipper, Professor Juniper,
Old Cemetery, Froakie/Frogadier/Greninja, Lucky Helmet, Magnemite -- each
checked against its printed text, including the cases where it should NOT work."""
import unittest
from unittest.mock import patch

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table
from spirit.game.attributes import AttrID, PokemonTypes
from spirit.game.data_utils import Attack, def_for
from spirit.game.models.board import EnergyEntity
from spirit.game.session.effects import EffectContext
from spirit.tools.effect_smoke import P1, P2

W, F, P, L, D = (PokemonTypes.WATER, PokemonTypes.FIRE, PokemonTypes.PSYCHIC,
                 PokemonTypes.LIGHTNING, PokemonTypes.DARKNESS)

ACADEMY = 'SV065.AcademyatNight_54'
TRUBBISH_VIV, TRUBBISH_GRI = 'SWSH4.Trubbish_110', 'SM2.Trubbish_50'
DRAMPA = 'SM12.Drampa_159'
BROCK = 'SV09.BrocksScouting_146'
DRAGONIUM = 'SM12.DragoniumZDragonClaw_190'
MARSHTOMP = 'SWSH8.Marshtomp_63'
WINGULL, PELIPPER = 'SV2.Wingull_158', 'SV2.Pelipper_159'
JUNIPER = 'BW10.ProfessorJuniper_84'
CEMETERY = 'SWSH6.OldCemetery_147'
FROAKIE, FROGADIER, GRENINJA = 'SV3.Froakie_56', 'SM6.Frogadier_23', 'XY1.Greninja_41'
HELMET = 'SV06.LuckyHelmet_158'
MAGNEMITE = 'SM12.Magnemite_68'
ULTRA_BALL = 'BW10.UltraBall_90'


def name(card):
    return def_for(card.archetype_id).display_name


class Chunk8(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    def neutral(self, p, hp=400):
        p.set_attribute(AttrID.WEAKNESS_TYPES, [])
        p.set_attribute(AttrID.RESISTANCE_TYPES, [])
        if hp is not None:
            p.set_attribute(AttrID.HP, hp)
        return p

    def table(self):
        t = Table(self)
        self.opp = self.neutral(t.put(self.filler, P2, 'active'))
        return t

    def took(self, p, start=400):
        return start - p.get_attribute(AttrID.HP, 0)

    def filler_attack(self):
        for a in def_for(self.opp.archetype_id).abilities:
            if isinstance(a, Attack) and a.damage:
                return a.title, a.damage
        raise AssertionError('filler has no damaging attack')

    def aim(self, t, target):
        """Steer both Pokémon choosers (choose_pokemon and card-browser picks)."""
        t.pokemon = lambda cands, prompt: target if target in cands else cands[0]
        t.picks = lambda cards, count, prompt, display: (
            [target] if target in cards else list(cards)[:count])

    def is_energy(self, card, kind):
        return card.archetype_id.lower() == self.energies[kind.value].lower()

    # --- Academy at Night (SFA 54) -------------------------------------------
    def stadium_entry(self, t, stadium, pid=P1):
        return next(iter(t.offers(stadium, None, pid)), None)

    async def test_academy_puts_hand_card_on_top_once_per_turn(self):
        t = self.table()
        stadium = t.stadium(ACADEMY, P2)       # opponent's Stadium: still usable
        t.put(self.filler, P1, 'active')
        a = t.put(JUNIPER, P1, 'hand')
        b = t.put(ULTRA_BALL, P1, 'hand')
        t.picks = lambda cards, count, prompt, display: [b]
        await t.do(self.stadium_entry(t, stadium))
        self.assertIs(t.zone(P1, 'deck')[-1], b)
        self.assertEqual(t.zone(P1, 'hand'), [a])
        self.assertIsNone(self.stadium_entry(t, stadium))   # once per turn

    async def test_academy_each_player_on_their_turn(self):
        t = self.table()
        stadium = t.stadium(ACADEMY, P1)
        t.put(self.filler, P1, 'active')
        t.put(ULTRA_BALL, P1, 'hand')
        await t.do(self.stadium_entry(t, stadium))
        t.next_turn()
        c = t.put(JUNIPER, P2, 'hand')
        entry = self.stadium_entry(t, stadium, P2)
        self.assertIsNotNone(entry)
        await t.do(entry, pid=P2)
        self.assertIs(t.zone(P2, 'deck')[-1], c)

    async def test_academy_not_offered_with_empty_hand(self):
        t = self.table()
        stadium = t.stadium(ACADEMY, P1)
        t.put(self.filler, P1, 'active')
        self.assertIsNone(self.stadium_entry(t, stadium))

    # --- Trubbish (VIV 110): Lucky Find --------------------------------------
    async def test_trubbish_lucky_find_items_only(self):
        t = self.table()
        trub = self.neutral(t.put(TRUBBISH_VIV, P1, 'active'))
        t.energy(trub, D, 2)
        ball = t.deck(P1, [ULTRA_BALL, self.filler, JUNIPER])[0]
        seen = {}

        def picks(cards, count, prompt, display):
            seen['names'] = set(t.names(cards))
            return [ball]
        t.picks = picks
        await t.attack(trub, 'Lucky Find')
        self.assertIn(ball, t.zone(P1, 'hand'))
        self.assertNotIn('Professor Juniper', seen['names'])
        self.assertNotIn(name(t.put(self.filler, P1, 'discard')), seen['names'])
        self.assertEqual(self.took(self.opp), 0)

    # --- Drampa (CEC 159): Dragon Arcana -------------------------------------
    async def test_drampa_dragon_arcana_two_types(self):
        t = self.table()
        drampa = self.neutral(t.put(DRAMPA, P1, 'active'))
        t.energy(drampa, W, 2)
        t.energy(drampa, F, 1)
        await t.attack(drampa, 'Dragon Arcana')
        self.assertEqual(self.took(self.opp), 140)

    async def test_drampa_dragon_arcana_one_type(self):
        t = self.table()
        drampa = self.neutral(t.put(DRAMPA, P1, 'active'))
        t.energy(drampa, W, 3)
        await t.attack(drampa, 'Dragon Arcana')
        self.assertEqual(self.took(self.opp), 70)

    # --- Trubbish (GRI 50): Stomp Off ----------------------------------------
    async def test_trubbish_stomp_off_discards_opponents_top_card(self):
        t = self.table()
        trub = self.neutral(t.put(TRUBBISH_GRI, P1, 'active'))
        t.energy(trub, P, 1)
        top = t.deck(P2, [JUNIPER])[0]
        mine = len(t.zone(P1, 'deck'))
        theirs = len(t.zone(P2, 'deck'))
        await t.attack(trub, 'Stomp Off')
        self.assertIn(top, t.zone(P2, 'discard'))
        self.assertEqual(len(t.zone(P2, 'deck')), theirs - 1)
        self.assertEqual(len(t.zone(P1, 'deck')), mine)
        self.assertEqual(self.took(self.opp), 0)

    # --- Brock's Scouting (JTG 146) ------------------------------------------
    async def test_brock_two_basics(self):
        t = self.table()
        t.put(self.filler, P1, 'active')
        b1, b2, evo = t.deck(P1, [FROAKIE, WINGULL, FROGADIER])
        brock = t.put(BROCK, P1, 'hand')
        seen = {}

        def picks(cards, count, prompt, display):
            seen['names'], seen['count'] = t.names(cards), count
            return [c for c in cards if c in (b1, b2)]
        t.picks = picks
        t.yes = True
        await t.play(brock)
        self.assertEqual(seen['count'], 2)
        self.assertNotIn('Frogadier', seen['names'])
        self.assertIn(b1, t.zone(P1, 'hand'))
        self.assertIn(b2, t.zone(P1, 'hand'))
        self.assertIn(evo, t.zone(P1, 'deck'))

    async def test_brock_one_evolution(self):
        t = self.table()
        t.put(self.filler, P1, 'active')
        b1, evo, evo2 = t.deck(P1, [FROAKIE, FROGADIER, PELIPPER])
        brock = t.put(BROCK, P1, 'hand')
        seen = {}

        def picks(cards, count, prompt, display):
            seen['names'], seen['count'] = t.names(cards), count
            return cards[:count]
        t.picks = picks
        t.yes = False
        await t.play(brock)
        self.assertEqual(seen['count'], 1)
        self.assertNotIn('Froakie', seen['names'])
        self.assertEqual(len([c for c in t.zone(P1, 'hand') if c in (evo, evo2)]), 1)
        self.assertIn(b1, t.zone(P1, 'deck'))

    # --- Dragonium Z: Dragon Claw (CEC 190) ----------------------------------
    async def test_dragonium_destructive_drake_on_dragon_claw_user(self):
        t = self.table()
        drampa = self.neutral(t.put(DRAMPA, P1, 'active'))
        basics = t.energy(drampa, W, 2) + [t.energy(drampa, F, 1)]
        await t.play(t.put(DRAGONIUM, P1, 'hand'), targets=[drampa.entity_id])
        offer = t.attack_offer(drampa, 'Destructive Drake-GX')
        self.assertIsNotNone(offer)
        await t.do(offer)
        self.assertEqual(self.took(self.opp), 240)
        for e in basics:
            self.assertIn(e, t.zone(P1, 'discard'))
        self.assertFalse([c for c in drampa.children if isinstance(c, EnergyEntity)])

    async def test_dragonium_not_usable_without_dragon_claw(self):
        t = self.table()
        mag = self.neutral(t.put(MAGNEMITE, P1, 'active'))
        t.energy(mag, W, 3)
        await t.play(t.put(DRAGONIUM, P1, 'hand'), targets=[mag.entity_id])
        self.assertIsNone(t.attack_offer(mag, 'Destructive Drake-GX'))

    async def test_dragonium_gx_once_per_game(self):
        t = self.table()
        drampa = self.neutral(t.put(DRAMPA, P1, 'active'))
        t.energy(drampa, W, 3)
        await t.play(t.put(DRAGONIUM, P1, 'hand'), targets=[drampa.entity_id])
        await t.attack(drampa, 'Destructive Drake-GX')
        t.next_turn()
        t.next_turn()
        t.energy(drampa, W, 3)
        self.assertIsNone(t.attack_offer(drampa, 'Destructive Drake-GX'))

    # --- Marshtomp (FST 63): Energy Loop -------------------------------------
    async def test_marshtomp_energy_loop(self):
        t = self.table()
        mt = self.neutral(t.put(MARSHTOMP, P1, 'active'))
        energies = t.energy(mt, W, 3)
        await t.attack(mt, 'Energy Loop')
        self.assertEqual(self.took(self.opp), 80)
        back = [e for e in energies if e in t.zone(P1, 'hand')]
        self.assertEqual(len(back), 1)
        self.assertEqual(len([c for c in mt.children if isinstance(c, EnergyEntity)]), 2)

    async def test_marshtomp_mud_slap_keeps_energy(self):
        t = self.table()
        mt = self.neutral(t.put(MARSHTOMP, P1, 'active'))
        t.energy(mt, W, 3)
        await t.attack(mt, 'Mud-Slap')
        self.assertEqual(self.took(self.opp), 30)
        self.assertEqual(t.zone(P1, 'hand'), [])

    # --- Pelipper (PAL 159): Hearsay -----------------------------------------
    async def _pelipper(self, option_label):
        t = self.table()
        gull = t.put(WINGULL, P1, 'active')
        in_discard = t.put(JUNIPER, P1, 'discard')
        t.put(ULTRA_BALL, P1, 'discard')
        in_deck = t.deck(P1, [BROCK])[0]
        peli = t.put(PELIPPER, P1, 'hand')
        menus = []

        async def choose(ctx, prompt, buttons, *a, **k):
            menus.append(list(buttons))
            return next(i for i, b in enumerate(buttons) if option_label in b)
        with patch.object(EffectContext, 'choose', choose):
            await t.play(peli, targets=[gull.entity_id])
        return t, peli, in_discard, in_deck, menus

    async def test_pelipper_hearsay_from_discard(self):
        t, peli, in_discard, in_deck, menus = await self._pelipper('discard')
        self.assertEqual(name(t.active(P1)), 'Pelipper')
        self.assertIn(in_discard, t.zone(P1, 'hand'))
        self.assertIn(in_deck, t.zone(P1, 'deck'))

    async def test_pelipper_hearsay_from_deck(self):
        t, peli, in_discard, in_deck, menus = await self._pelipper('deck')
        self.assertIn(in_deck, t.zone(P1, 'hand'))
        self.assertIn(in_discard, t.zone(P1, 'discard'))

    async def test_pelipper_hearsay_may_decline(self):
        t, peli, in_discard, in_deck, menus = await self._pelipper("Don't")
        self.assertEqual(name(t.active(P1)), 'Pelipper')
        self.assertNotIn(in_discard, t.zone(P1, 'hand'))
        self.assertNotIn(in_deck, t.zone(P1, 'hand'))

    async def test_pelipper_hearsay_not_offered_later(self):
        t = self.table()
        peli = t.put(PELIPPER, P1, 'active')
        t.put(JUNIPER, P1, 'discard')
        self.assertIsNone(t.ability_offer(peli, 'Hearsay'))

    # --- Professor Juniper (PLB 84) ------------------------------------------
    async def test_juniper_discards_hand_draws_7(self):
        t = self.table()
        t.put(self.filler, P1, 'active')
        others = [t.put(ULTRA_BALL, P1, 'hand') for _ in range(3)]
        jun = t.put(JUNIPER, P1, 'hand')
        await t.play(jun)
        for c in others:
            self.assertIn(c, t.zone(P1, 'discard'))
        self.assertIn(jun, t.zone(P1, 'discard'))
        self.assertEqual(len(t.zone(P1, 'hand')), 7)

    async def test_juniper_small_deck_draws_what_is_left(self):
        t = Table(self, filler_deck=3)
        self.opp = self.neutral(t.put(self.filler, P2, 'active'))
        t.put(self.filler, P1, 'active')
        jun = t.put(JUNIPER, P1, 'hand')
        await t.play(jun)
        self.assertEqual(len(t.zone(P1, 'hand')), 3)
        self.assertEqual(t.zone(P1, 'deck'), [])

    # --- Old Cemetery (CRE 147) ----------------------------------------------
    async def test_old_cemetery_non_psychic_takes_20_both_players(self):
        t = self.table()
        t.stadium(CEMETERY, P1)
        mine = self.neutral(t.put(self.filler, P1, 'active'))
        await t.play(t.put(t.basic_energy(W), P1, 'hand'), targets=[mine.entity_id])
        self.assertEqual(self.took(mine), 20)
        t.next_turn()
        await t.play(t.put(t.basic_energy(W), P2, 'hand'), pid=P2,
                     targets=[self.opp.entity_id])
        self.assertEqual(self.took(self.opp), 20)

    async def test_old_cemetery_psychic_unaffected(self):
        t = self.table()
        t.stadium(CEMETERY, P1)
        trub = self.neutral(t.put(TRUBBISH_GRI, P1, 'active'), hp=None)
        await t.play(t.put(t.basic_energy(P), P1, 'hand'), targets=[trub.entity_id])
        self.assertEqual(t.damage(trub), 0)
        self.assertEqual(len(trub.children), 1)

    # --- Froakie (OBF 56): Try Bouncing --------------------------------------
    async def test_froakie_try_bouncing(self):
        for heads, dmg in ((True, 30), (False, 0)):
            t = self.table()
            fro = self.neutral(t.put(FROAKIE, P1, 'active'))
            t.energy(fro, W, 1)
            t.heads = heads
            await t.attack(fro, 'Try Bouncing')
            with self.subTest(heads=heads):
                self.assertEqual(self.took(self.opp), dmg)

    # --- Frogadier (FLI 23): Gale Shuriken -----------------------------------
    async def test_frogadier_gale_shuriken_on_evolve(self):
        t = self.table()
        bench = self.neutral(t.put(self.filler, P2, 'bench'))
        fro = t.put(FROAKIE, P1, 'active')
        frog = t.put(FROGADIER, P1, 'hand')
        t.yes = True
        self.aim(t, bench)
        await t.play(frog, targets=[fro.entity_id])
        self.assertEqual(name(t.active(P1)), 'Frogadier')
        self.assertEqual(self.took(bench), 20)
        self.assertEqual(self.took(self.opp), 0)
        self.assertEqual(t.damage(t.active(P1)), 0)

    async def test_frogadier_gale_shuriken_may_decline(self):
        t = self.table()
        fro = t.put(FROAKIE, P1, 'active')
        frog = t.put(FROGADIER, P1, 'hand')
        t.yes = False
        await t.play(frog, targets=[fro.entity_id])
        self.assertEqual(name(t.active(P1)), 'Frogadier')
        self.assertEqual(self.took(self.opp), 0)

    async def test_frogadier_gale_shuriken_not_offered_later(self):
        t = self.table()
        frog = t.put(FROGADIER, P1, 'active')
        self.assertIsNone(t.ability_offer(frog, 'Gale Shuriken'))

    # --- Greninja (XY 41): Water Shuriken / Mist Slash -----------------------
    async def test_greninja_water_shuriken(self):
        t = self.table()
        bench = self.neutral(t.put(self.filler, P2, 'bench'))
        gren = self.neutral(t.put(GRENINJA, P1, 'active'))
        water = t.put(t.basic_energy(W), P1, 'hand')
        self.aim(t, bench)
        await t.use(gren, 'Water Shuriken')
        self.assertIn(water, t.zone(P1, 'discard'))
        self.assertEqual(self.took(bench), 30)
        self.assertEqual(self.took(self.opp), 0)
        # once during your turn
        t.put(t.basic_energy(W), P1, 'hand')
        self.assertIsNone(t.ability_offer(gren, 'Water Shuriken'))

    async def test_greninja_water_shuriken_needs_water_energy_in_hand(self):
        t = self.table()
        gren = self.neutral(t.put(GRENINJA, P1, 'active'))
        t.put(t.basic_energy(F), P1, 'hand')
        t.energy(gren, W, 1)                       # attached Water doesn't count
        entry = t.ability_offer(gren, 'Water Shuriken')
        if entry is not None:
            await t.do(entry)
        self.assertEqual(self.took(self.opp), 0)
        self.assertEqual(t.zone(P1, 'discard'), [])

    async def test_greninja_water_shuriken_from_bench(self):
        t = self.table()
        t.put(self.filler, P1, 'active')
        gren = self.neutral(t.put(GRENINJA, P1, 'bench'))
        t.put(t.basic_energy(W), P1, 'hand')
        await t.use(gren, 'Water Shuriken')
        self.assertEqual(self.took(self.opp), 30)

    async def test_greninja_mist_slash_ignores_weakness(self):
        t = self.table()
        self.opp.set_attribute(AttrID.WEAKNESS_TYPES, [W.value])
        gren = self.neutral(t.put(GRENINJA, P1, 'active'))
        t.energy(gren, W, 1)
        await t.attack(gren, 'Mist Slash')
        self.assertEqual(self.took(self.opp), 50)

    # --- Lucky Helmet (TWM 158) ----------------------------------------------
    async def test_lucky_helmet_draws_when_active_hit(self):
        t = self.table()
        mine = self.neutral(t.put(self.filler, P1, 'active'))
        await t.play(t.put(HELMET, P1, 'hand'), targets=[mine.entity_id])
        title, _ = self.filler_attack()
        t.energy(self.opp, W, 5)
        t.next_turn()
        before = len(t.zone(P1, 'hand'))
        await t.attack(self.opp, title, pid=P2)
        self.assertGreater(self.took(mine), 0)
        self.assertEqual(len(t.zone(P1, 'hand')), before + 2)

    async def test_lucky_helmet_draws_even_if_knocked_out(self):
        t = self.table()
        mine = self.neutral(t.put(self.filler, P1, 'active'), hp=10)
        t.put(self.filler, P1, 'bench')
        await t.play(t.put(HELMET, P1, 'hand'), targets=[mine.entity_id])
        title, _ = self.filler_attack()
        t.energy(self.opp, W, 5)
        t.next_turn()
        before = len(t.zone(P1, 'hand'))
        await t.attack(self.opp, title, pid=P2)
        self.assertIn(mine, t.zone(P1, 'discard'))
        self.assertEqual(len(t.zone(P1, 'hand')), before + 2)

    async def test_lucky_helmet_no_draw_on_ability_damage(self):
        t = self.table()
        mine = self.neutral(t.put(self.filler, P1, 'active'))
        await t.play(t.put(HELMET, P1, 'hand'), targets=[mine.entity_id])
        t.next_turn()
        gren = self.neutral(t.put(GRENINJA, P2, 'bench'))
        t.put(t.basic_energy(W), P2, 'hand')
        self.aim(t, mine)
        before = len(t.zone(P1, 'hand'))
        await t.use(gren, 'Water Shuriken', pid=P2)
        self.assertEqual(self.took(mine), 30)
        self.assertEqual(len(t.zone(P1, 'hand')), before)

    async def test_lucky_helmet_no_draw_when_benched(self):
        t = self.table()
        t.put(self.filler, P1, 'active')
        benched = self.neutral(t.put(self.filler, P1, 'bench'))
        await t.play(t.put(HELMET, P1, 'hand'), targets=[benched.entity_id])
        t.next_turn()
        frog_base = t.put(FROAKIE, P2, 'bench')
        frog = t.put(FROGADIER, P2, 'hand')
        t.yes = True
        self.aim(t, benched)
        before = len(t.zone(P1, 'hand'))
        await t.play(frog, pid=P2, targets=[frog_base.entity_id])
        self.assertEqual(self.took(benched), 20)
        self.assertEqual(len(t.zone(P1, 'hand')), before)

    # --- Magnemite (CEC 68): Mirror Shot -------------------------------------
    async def _mirror_shot(self, heads):
        t = self.table()
        mag = self.neutral(t.put(MAGNEMITE, P1, 'active'))
        t.energy(mag, L, 1)
        await t.attack(mag, 'Mirror Shot')
        self.assertEqual(self.took(self.opp), 10)
        title, _ = self.filler_attack()
        t.energy(self.opp, W, 5)
        t.next_turn()
        flips = []

        def coins(player_id, count):
            flips.append(player_id)
            return [heads] * count
        with patch.object(t.session, '_attack_attempt_coins', coins):
            await t.attack(self.opp, title, pid=P2)
        return t, mag, flips

    async def test_magnemite_mirror_shot_tails_blocks(self):
        t, mag, flips = await self._mirror_shot(False)
        self.assertEqual(flips, [P2])
        self.assertEqual(self.took(mag), 0)

    async def test_magnemite_mirror_shot_heads_attack_happens(self):
        t, mag, flips = await self._mirror_shot(True)
        self.assertEqual(flips, [P2])
        self.assertGreater(self.took(mag), 0)


if __name__ == '__main__':
    unittest.main()
