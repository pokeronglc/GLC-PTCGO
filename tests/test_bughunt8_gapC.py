"""Bug hunt round 8, gap group C: Galarian Zigzagoon, Garbodor (ME4), Lucky Egg,
Manectric, Ninetales, Octillery, Pyukumuku, Reshiram, Rocky Helmet, Serperior,
Talonflame, Zoroark -- the never-exercised text of each card, including the
cases where it should NOT work."""
import unittest
from unittest.mock import AsyncMock, patch

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table, POISONED
from spirit.game.attributes import AttrID, PokemonTypes
from spirit.game.data_utils import Attack, def_for
from spirit.game.session.effects import EffectContext
from spirit.game.session.passives import effective_pokemon_types
from spirit.tools.effect_smoke import P1, P2

WATER, FIRE, GRASS, LIGHT, DARK = (PokemonTypes.WATER, PokemonTypes.FIRE, PokemonTypes.GRASS,
                                   PokemonTypes.LIGHTNING, PokemonTypes.DARKNESS)

ZIGZAGOON = 'SWSH1.GalarianZigzagoon_117'
GARBODOR = 'ME4.Garbodor_57'
LUCKY_EGG = 'SWSH1.LuckyEgg_167'
MANECTRIC, ELECTRIKE = 'SM7.Manectric_52', 'BW6.Electrike_41'
NINETALES = 'BW11.Ninetales_21'
OCTILLERY = 'SV09.Octillery_34'
PYUKUMUKU = 'SM1.Pyukumuku_47'
RESHIRAM, ZEKROM = 'BW9.Reshiram_17', 'BW9.Zekrom_39'
HELMETS = ['BW3.RockyHelmet_94', 'BW7.RockyHelmet_133', 'BW7.RockyHelmet_153',
           'SV1.RockyHelmet_193', 'SWSH4.RockyHelmet_159']
SERPERIOR = 'BW1.Serperior_6'
TALONFLAME = 'XY11.Talonflame_96'
ZOROARK = 'SM9.Zoroark_91'
THERAPEUTIC = 'SV2.TherapeuticEnergy_193'


class MinTable(Table):
    """Table that also records the `minimum` passed to each card pick."""

    def _patches(self):
        out = super()._patches()
        table = self
        table.minimums = []
        inner = out[0].new

        async def choose_cards(ctx, cards, count, minimum=None, *a, **k):
            table.minimums.append(minimum)
            return await inner(ctx, cards, count, minimum, *a, **k)
        out[0] = patch.object(EffectContext, 'choose_cards', choose_cards)
        return out


class GapC(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    def table(self, cls=Table, opp=None):
        t = cls(self)
        self.opp = t.put(opp or self.filler, P2, 'active')
        self.neutral(self.opp, 400)
        return t

    @staticmethod
    def neutral(p, hp=None):
        p.set_attribute(AttrID.WEAKNESS_TYPES, [])
        p.set_attribute(AttrID.RESISTANCE_TYPES, [])
        if hp is not None:
            p.set_attribute(AttrID.HP, hp)

    def mine(self, t, spec, kind, count, zone='active', hp=None):
        p = t.put(spec, P1, zone)
        self.neutral(p, hp)
        if count:
            t.energy(p, kind, count)
        return p

    def filler_attack(self):
        for a in def_for(self.opp.archetype_id).abilities:
            if isinstance(a, Attack) and a.damage:
                return a.title, a.damage
        raise AssertionError('filler has no damaging attack')

    async def opp_hits(self, t):
        title, dmg = self.filler_attack()
        t.energy(self.opp, WATER, 5)
        t.next_turn()
        await t.attack(self.opp, title, pid=P2)
        return dmg

    def clear_hand(self, t, pid=P1):
        area = t.board.find_player_area(pid, 'hand')
        for c in list(area.children):
            area.remove_child(c)

    def is_energy_of(self, card, kind):
        return card.archetype_id.lower() == self.energies[kind.value].lower()

    def lost(self, t, p, start=400):
        return start - t.hp(p)

    # --- Galarian Zigzagoon SSH 117: Surprise Attack ----------------------------
    async def test_zigzagoon_surprise_attack_heads_30_tails_nothing(self):
        for heads, want in ((True, 30), (False, 0)):
            t = self.table()
            zz = self.mine(t, ZIGZAGOON, DARK, 2)
            t.heads = heads
            await t.attack(zz, 'Surprise Attack')
            with self.subTest(heads=heads):
                self.assertEqual(self.lost(t, self.opp), want)

    # --- Garbodor ME4 57: Gloomy Garbage ---------------------------------------
    async def test_garbodor_reduces_tooled_opponent_attack_by_20(self):
        for zone in ('active', 'bench'):
            t = self.table()
            if zone == 'active':
                target = self.mine(t, GARBODOR, DARK, 0, hp=400)
            else:
                self.mine(t, GARBODOR, DARK, 0, zone='bench', hp=400)
                target = self.mine(t, self.filler, DARK, 0, hp=400)
            t.attach(LUCKY_EGG, self.opp)
            dmg = await self.opp_hits(t)
            with self.subTest(garbodor=zone):
                self.assertEqual(self.lost(t, target), dmg - 20)

    # FIXED Oct 13 (was: Gloomy Garbage ignores "that has a Pokémon Tool attached" -- reduces every opposing Active attack.
    async def test_garbodor_no_tool_no_reduction(self):
        t = self.table()
        target = self.mine(t, GARBODOR, DARK, 0, hp=400)
        dmg = await self.opp_hits(t)
        self.assertEqual(self.lost(t, target), dmg)

    async def test_garbodor_before_weakness(self):
        t = self.table()
        target = self.mine(t, self.filler, DARK, 0, hp=400)
        self.mine(t, GARBODOR, DARK, 0, zone='bench', hp=400)
        opp_type = effective_pokemon_types(t.board, self.opp)[0]
        target.set_attribute(AttrID.WEAKNESS_TYPES, [PokemonTypes(opp_type)])
        t.attach(LUCKY_EGG, self.opp)
        dmg = await self.opp_hits(t)
        self.assertEqual(self.lost(t, target), (dmg - 20) * 2)

    async def test_garbodor_does_not_reduce_own_tooled_attacks(self):
        t = self.table()
        zz = self.mine(t, ZIGZAGOON, DARK, 2)
        self.mine(t, GARBODOR, DARK, 0, zone='bench')
        t.attach(LUCKY_EGG, zz)
        t.heads = True
        await t.attack(zz, 'Surprise Attack')
        self.assertEqual(self.lost(t, self.opp), 30)

    # --- Lucky Egg SSH 167 -----------------------------------------------------
    async def test_lucky_egg_draws_to_seven_when_ko_by_attack(self):
        t = self.table()
        holder = self.mine(t, self.filler, DARK, 0, hp=10)
        self.mine(t, self.filler, DARK, 0, zone='bench')
        egg = t.put(LUCKY_EGG, P1, 'hand')
        await t.play(egg, targets=[holder.entity_id])
        self.assertIn(egg, t.attached(holder))
        self.clear_hand(t)
        t.put(self.item, P1, 'hand')
        t.put(self.item, P1, 'hand')
        await self.opp_hits(t)
        self.assertNotIn(holder, t.zone(P1, 'active'))
        self.assertEqual(len(t.zone(P1, 'hand')), 7)

    async def test_lucky_egg_no_draw_on_poison_ko(self):
        t = self.table()
        holder = self.mine(t, self.filler, DARK, 0, hp=10)
        self.mine(t, self.filler, DARK, 0, zone='bench')
        await t.play(t.put(LUCKY_EGG, P1, 'hand'), targets=[holder.entity_id])
        self.clear_hand(t)
        t.put(self.item, P1, 'hand')
        holder.set_attribute(AttrID.SPECIAL_CONDITIONS, [POISONED])
        await t.checkup()
        self.assertNotIn(holder, t.zone(P1, 'active'))
        self.assertEqual(len(t.zone(P1, 'hand')), 1)

    async def test_lucky_egg_no_draw_when_survives(self):
        t = self.table()
        holder = self.mine(t, self.filler, DARK, 0, hp=400)
        await t.play(t.put(LUCKY_EGG, P1, 'hand'), targets=[holder.entity_id])
        self.clear_hand(t)
        await self.opp_hits(t)
        self.assertIs(t.active(P1), holder)
        self.assertEqual(len(t.zone(P1, 'hand')), 0)

    # --- Manectric CES 52: Double Charge / evolve ------------------------------
    async def test_manectric_evolves_from_electrike(self):
        t = self.table()
        ele = self.mine(t, ELECTRIKE, LIGHT, 0)
        man = t.put(MANECTRIC, P1, 'hand')
        await t.play(man, targets=[ele.entity_id])
        self.assertEqual(t.names([t.active(P1)]), ['Manectric'])

    async def test_manectric_double_charge_two_to_one_benched(self):
        t = self.table()
        man = self.mine(t, MANECTRIC, LIGHT, 1)
        b1 = self.mine(t, self.filler, DARK, 0, zone='bench')
        self.mine(t, self.filler, DARK, 0, zone='bench')
        self.clear_hand(t)
        e1 = t.put(t.basic_energy(WATER), P1, 'hand')
        e2 = t.put(t.basic_energy(FIRE), P1, 'hand')
        e3 = t.put(t.basic_energy(GRASS), P1, 'hand')
        t.pokemon = lambda cands, prompt: b1
        t.picks = lambda cards, count, prompt, display: [c for c in cards if c in (e1, e2)][:count]
        await t.attack(man, 'Double Charge')
        self.assertEqual(self.lost(t, self.opp), 40)
        self.assertIn(e1, t.attached(b1))
        self.assertIn(e2, t.attached(b1))
        self.assertIn(e3, t.zone(P1, 'hand'))
        self.assertNotIn(e1, t.attached(man))

    async def test_manectric_double_charge_never_special_energy(self):
        t = self.table()
        man = self.mine(t, MANECTRIC, LIGHT, 1)
        b1 = self.mine(t, self.filler, DARK, 0, zone='bench')
        self.clear_hand(t)
        sp = t.put(THERAPEUTIC, P1, 'hand')
        seen = []
        t.picks = lambda cards, count, prompt, display: (seen.extend(cards), list(cards)[:count])[1]
        await t.attack(man, 'Double Charge')
        self.assertNotIn(sp, seen)
        self.assertIn(sp, t.zone(P1, 'hand'))
        self.assertEqual(self.lost(t, self.opp), 40)

    async def test_manectric_double_charge_may_attach_none(self):
        t = self.table()
        man = self.mine(t, MANECTRIC, LIGHT, 1)
        b1 = self.mine(t, self.filler, DARK, 0, zone='bench')
        self.clear_hand(t)
        e1 = t.put(t.basic_energy(WATER), P1, 'hand')
        t.yes = False
        t.picks = lambda cards, count, prompt, display: []
        await t.attack(man, 'Double Charge')
        self.assertIn(e1, t.zone(P1, 'hand'))
        self.assertEqual(self.lost(t, self.opp), 40)

    async def test_manectric_electric_start_flags(self):
        d = fixtures.definition(MANECTRIC)
        self.assertTrue(d.setup_as_active)
        self.assertTrue(d.setup_as_bench)
        self.assertTrue(d.setup_second_player_only)

    async def test_manectric_electric_start_only_when_going_second(self):
        t = self.table()
        man = t.put(MANECTRIC, P1, 'hand')
        for first, allowed in ((P2, True), (P1, False)):
            t.board.setup_first_player_id = first
            with self.subTest(first=first):
                self.assertEqual(man in t.board.setup_active_candidates(P1), allowed)
                self.assertEqual(man in t.board.setup_bench_candidates(P1), allowed)

    # --- Ninetales LTR 21: Color Coordination ----------------------------------
    # FIXED Oct 13 (was: Color Coordination never adds +40 (condition clause unsupported, bonus silently dropped).
    async def test_ninetales_matching_basic_energy_plus_40(self):
        t = self.table(opp=PYUKUMUKU)          # Water Defending Pokémon
        nt = self.mine(t, NINETALES, FIRE, 2)
        t.energy(nt, WATER, 1)
        await t.attack(nt, 'Color Coordination')
        self.assertEqual(self.lost(t, self.opp), 90)

    async def test_ninetales_no_matching_energy_base_50(self):
        t = self.table(opp=PYUKUMUKU)
        nt = self.mine(t, NINETALES, FIRE, 3)
        await t.attack(nt, 'Color Coordination')
        self.assertEqual(self.lost(t, self.opp), 50)

    # --- Octillery JTG 34: Aqua Wash -------------------------------------------
    async def test_octillery_aqua_wash_returns_chosen_energy_to_opp_hand(self):
        t = self.table()
        oc = self.mine(t, OCTILLERY, WATER, 1)
        ew, ef = t.energy(self.opp, WATER, 1), t.energy(self.opp, FIRE, 1)
        t.picks = lambda cards, count, prompt, display: [ef]
        await t.attack(oc, 'Aqua Wash')
        self.assertEqual(self.lost(t, self.opp), 20)
        self.assertIn(ef, t.zone(P2, 'hand'))
        self.assertIn(ew, t.attached(self.opp))
        self.assertNotIn(ef, t.zone(P1, 'hand'))

    async def test_octillery_aqua_wash_is_optional(self):
        t = self.table(MinTable)
        oc = self.mine(t, OCTILLERY, WATER, 1)
        e = t.energy(self.opp, WATER, 1)
        t.picks = lambda cards, count, prompt, display: []
        await t.attack(oc, 'Aqua Wash')
        self.assertIn(0, t.minimums)          # "You may": pick is optional
        self.assertIn(e, t.attached(self.opp))
        self.assertEqual(self.lost(t, self.opp), 20)

    async def test_octillery_aqua_wash_no_energy_still_damages(self):
        t = self.table()
        oc = self.mine(t, OCTILLERY, WATER, 1)
        await t.attack(oc, 'Aqua Wash')
        self.assertEqual(self.lost(t, self.opp), 20)
        self.assertEqual(len(t.zone(P2, 'hand')), 0)

    # --- Pyukumuku SUM 47: Continuous Tumble -----------------------------------
    async def test_pyukumuku_continuous_tumble_30_per_heads(self):
        for heads in (0, 1, 3):
            t = self.table()
            py = self.mine(t, PYUKUMUKU, WATER, 1)
            with patch.object(EffectContext, 'flip_until_tails', AsyncMock(return_value=heads)):
                await t.attack(py, 'Continuous Tumble')
            with self.subTest(heads=heads):
                self.assertEqual(self.lost(t, self.opp), 30 * heads)

    # --- Reshiram PLF 17: Fusion Flare -----------------------------------------
    async def test_reshiram_fusion_flare_with_zekrom_on_bench(self):
        t = self.table()
        rs = self.mine(t, RESHIRAM, FIRE, 4)
        t.put(ZEKROM, P1, 'bench')
        await t.attack(rs, 'Fusion Flare')
        self.assertEqual(self.lost(t, self.opp), 120)

    async def test_reshiram_fusion_flare_without_own_benched_zekrom(self):
        for where in ('none', 'opp_bench', 'hand'):
            t = self.table()
            rs = self.mine(t, RESHIRAM, FIRE, 4)
            t.put(self.filler, P1, 'bench')
            if where == 'opp_bench':
                t.put(ZEKROM, P2, 'bench')
            elif where == 'hand':
                t.put(ZEKROM, P1, 'hand')
            await t.attack(rs, 'Fusion Flare')
            with self.subTest(where=where):
                self.assertEqual(self.lost(t, self.opp), 80)

    # --- Rocky Helmet ----------------------------------------------------------
    async def test_rocky_helmet_two_counters_on_attacker(self):
        for spec in HELMETS:
            t = self.table()
            holder = self.mine(t, self.filler, DARK, 0, hp=400)
            await t.play(t.put(spec, P1, 'hand'), targets=[holder.entity_id])
            my_type = effective_pokemon_types(t.board, holder)[0]
            self.opp.set_attribute(AttrID.WEAKNESS_TYPES, [PokemonTypes(my_type)])   # counters ignore Weakness
            await self.opp_hits(t)
            with self.subTest(spec=spec):
                self.assertEqual(self.lost(t, self.opp), 20)

    async def test_rocky_helmet_even_if_holder_knocked_out(self):
        t = self.table()
        holder = self.mine(t, self.filler, DARK, 0, hp=10)
        self.mine(t, self.filler, DARK, 0, zone='bench')
        await t.play(t.put(HELMETS[0], P1, 'hand'), targets=[holder.entity_id])
        await self.opp_hits(t)
        self.assertNotIn(holder, t.zone(P1, 'active'))
        self.assertEqual(self.lost(t, self.opp), 20)

    async def test_rocky_helmet_no_counters_when_attack_does_no_damage(self):
        t = self.table()
        holder = self.mine(t, self.filler, DARK, 0, hp=400)
        await t.play(t.put(HELMETS[0], P1, 'hand'), targets=[holder.entity_id])
        zz = t.put(ZIGZAGOON, P2, 'bench')
        self.neutral(zz, 400)
        t.energy(zz, DARK, 2)
        board = t.board
        board.move_card(self.opp.entity_id, board.find_player_area(P2, 'bench').entity_id)
        board.move_card(zz.entity_id, board.find_player_area(P2, 'activePokemonArea').entity_id)
        t.next_turn()
        t.heads = False
        await t.attack(zz, 'Surprise Attack', pid=P2)
        self.assertEqual(self.lost(t, holder), 0)
        self.assertEqual(self.lost(t, zz), 0)

    # --- Serperior EPO/BLW 6: Leaf Tornado -------------------------------------
    async def test_serperior_leaf_tornado_moves_grass_any_way(self):
        t = self.table()
        sp = self.mine(t, SERPERIOR, GRASS, 2)
        b1 = self.mine(t, self.filler, DARK, 0, zone='bench')
        b2 = self.mine(t, self.filler, DARK, 0, zone='bench')
        g3 = t.energy(b1, GRASS, 1)
        g1, g2 = [c for c in sp.children if self.is_energy_of(c, GRASS)]
        plan = iter([(g1, b1), (g3, b2), (None, None)])
        current = {}

        def picks(cards, count, prompt, display):
            e, dest = next(plan)
            current['dest'] = dest
            return [e] if e is not None else []
        t.picks = picks
        t.pokemon = lambda cands, prompt: current['dest']
        await t.attack(sp, 'Leaf Tornado')
        self.assertEqual(self.lost(t, self.opp), 60)
        self.assertIn(g1, t.attached(b1))
        self.assertIn(g3, t.attached(b2))
        self.assertIn(g2, t.attached(sp))

    async def test_serperior_leaf_tornado_only_grass_offered(self):
        t = self.table()
        sp = self.mine(t, SERPERIOR, GRASS, 2)
        b1 = self.mine(t, self.filler, DARK, 0, zone='bench')
        w = t.energy(b1, WATER, 1)
        seen = []

        def picks(cards, count, prompt, display):
            seen.extend(cards)
            return []
        t.picks = picks
        await t.attack(sp, 'Leaf Tornado')
        self.assertNotIn(w, seen)
        self.assertTrue(seen)
        self.assertIn(w, t.attached(b1))

    # --- Talonflame STS 96: Gale Wings -----------------------------------------
    async def test_talonflame_gale_wings_setup_active_only(self):
        t = self.table()
        tf = t.put(TALONFLAME, P1, 'hand')
        for first in (P1, P2):        # no "if you go second" condition
            t.board.setup_first_player_id = first
            with self.subTest(first=first):
                self.assertIn(tf, t.board.setup_active_candidates(P1))
                self.assertNotIn(tf, t.board.setup_bench_candidates(P1))
                self.assertNotIn(tf, t.board.basic_pokemon_in_hand(P1))

    async def test_talonflame_not_playable_to_bench_mid_game(self):
        t = self.table()
        self.mine(t, self.filler, DARK, 0)
        tf = t.put(TALONFLAME, P1, 'hand')
        self.assertFalse(t.offers(tf, 'DefaultPokemonPlayAbility'))

    # --- Zoroark BKT/TEU 91: Night Punishment ----------------------------------
    async def test_zoroark_night_punishment_20_per_pokemon_in_own_discard(self):
        t = self.table()
        zo = self.mine(t, ZOROARK, DARK, 3)
        for _ in range(3):
            t.put(self.filler, P1, 'discard')
        t.put(self.item, P1, 'discard')
        t.put(t.basic_energy(WATER), P1, 'discard')
        for _ in range(4):
            t.put(self.filler, P2, 'discard')
        await t.attack(zo, 'Night Punishment')
        self.assertEqual(self.lost(t, self.opp), 60)

    async def test_zoroark_night_punishment_capped_at_200(self):
        for n, want in ((10, 200), (11, 200), (0, 0)):
            t = self.table()
            zo = self.mine(t, ZOROARK, DARK, 3)
            for _ in range(n):
                t.put(self.filler, P1, 'discard')
            await t.attack(zo, 'Night Punishment')
            with self.subTest(n=n):
                self.assertEqual(self.lost(t, self.opp), want)


if __name__ == '__main__':
    unittest.main()
