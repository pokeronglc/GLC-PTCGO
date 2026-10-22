"""Bug hunt round 7, chunk 21: Hippowdon, N's Vanillite line, Accelgor,
Lilligant, Spell Tag, Togetic, Slowbro, Starmie, Professor Sada's Vitality,
Porygon, Hippopotas, Tapu Bulu, Burning Energy -- each checked against its
printed text, including the cases where it should NOT work."""
import unittest
from unittest.mock import patch

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table, ASLEEP
from spirit.game.attributes import AttrID, PokemonTypes
from spirit.game.data_utils import Attack, def_for
from spirit.game.session.passives import effective_max_hp
from spirit.tools.effect_smoke import P1, P2

F, W, G, R, P = (PokemonTypes.FIGHTING, PokemonTypes.WATER, PokemonTypes.GRASS,
                 PokemonTypes.FIRE, PokemonTypes.PSYCHIC)

HIPPOWDON, HIPPOPOTAS = 'SV10.Hippowdon_106', 'XY8.Hippopotas_83'
VANILLITE, VANILLISH, VANILLUXE = ('ME2PT5.NsVanillite_49', 'ME2PT5.NsVanillish_50',
                                   'ME2PT5.NsVanilluxe_51')
ACCELGOR, LILLIGANT = 'SWSH8.Accelgor_14', 'SV09.Lilligant_7'
SPELL_TAG, TOGETIC, SLOWBRO = 'SM8.SpellTag_190', 'SV3.Togetic_84', 'PGO.Slowbro_20'
STARMIE, SADA, PORYGON = 'SV035.Starmie_121', 'SV4.ProfessorSadasVitality_170', 'SV4.Porygon_142'
TAPU_BULU, BURNING = 'SV065.TapuBulu_6', 'XY8.BurningEnergy_151'
GREAT_TUSK, FLUTTER_MANE = 'SV05.GreatTusk_96', 'SV05.FlutterMane_78'   # Ancient Basics
CACNEA, CHARCADET, DRIFLOON = 'SV1.Cacnea_5', 'SV1.Charcadet_39', 'SV1.Drifloon_89'
SWITCH, WEEZING = 'SV1.Switch_194', 'SWSH2.GalarianWeezing_113'


class Chunk21(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    def neutral(self, p, hp=None):
        p.set_attribute(AttrID.WEAKNESS_TYPES, [])
        p.set_attribute(AttrID.RESISTANCE_TYPES, [])
        if hp is not None:
            p.set_attribute(AttrID.HP, hp)
        return p

    def table(self):
        t = Table(self)
        self.opp = self.neutral(t.put(self.filler, P2, 'active'), 400)
        return t

    def mine(self, t, spec, kind=None, count=0, zone='active'):
        p = self.neutral(t.put(spec, P1, zone))
        if count:
            t.energy(p, kind, count)
        return p

    def maxhp(self, t, p):
        return effective_max_hp(t.board, p)

    def hurt(self, t, p, dmg):
        p.set_attribute(AttrID.HP, self.maxhp(t, p) - dmg)
        return p

    def filler_attack(self):
        for a in def_for(self.opp.archetype_id).abilities:
            if isinstance(a, Attack) and a.damage:
                return a.title, a.damage
        raise AssertionError('filler has no damaging attack')

    async def opp_hits(self, t):
        title, dmg = self.filler_attack()
        t.energy(self.opp, W, 5)
        t.next_turn()
        await t.attack(self.opp, title, pid=P2)
        return dmg

    # --- Hippowdon (DRI 106): Super Sandstorm --------------------------------
    async def test_hippowdon_super_sandstorm_hits_damaged_benches_both_sides(self):
        t = self.table()
        h = self.mine(t, HIPPOWDON, F, 3)
        opp_hurt = self.hurt(t, self.neutral(t.put(self.filler, P2, 'bench')), 10)
        opp_clean = self.neutral(t.put(self.filler, P2, 'bench'))
        my_hurt = self.hurt(t, self.neutral(t.put(self.filler, P1, 'bench')), 10)
        my_clean = self.neutral(t.put(self.filler, P1, 'bench'))
        before = {p.entity_id: t.hp(p) for p in (opp_hurt, opp_clean, my_hurt, my_clean)}
        await t.attack(h, 'Super Sandstorm')
        self.assertEqual(400 - t.hp(self.opp), 150)
        self.assertEqual(before[opp_hurt.entity_id] - t.hp(opp_hurt), 40)
        self.assertEqual(before[my_hurt.entity_id] - t.hp(my_hurt), 40)
        self.assertEqual(t.hp(opp_clean), before[opp_clean.entity_id])
        self.assertEqual(t.hp(my_clean), before[my_clean.entity_id])
        self.assertEqual(t.hp(h), self.maxhp(t, h))

    # --- N's Vanillite (ASC 49): Call for Family ------------------------------
    async def test_vanillite_call_for_family_two_basics_only(self):
        t = self.table()
        v = self.mine(t, VANILLITE, W, 1)
        basics = t.deck(P1, [self.filler, self.filler, CACNEA])
        stage1 = t.deck(P1, [VANILLISH])[0]
        offered = []

        def picks(cards, count, prompt, display):
            offered.extend(cards)
            return [c for c in cards if c in basics][:count]
        t.picks = picks
        await t.attack(v, 'Call for Family')
        bench = t.zone(P1, 'bench')
        self.assertEqual(len(bench), 2)
        self.assertNotIn(stage1, offered)
        self.assertIn(stage1, t.zone(P1, 'deck'))

    # --- N's Vanillish (ASC 50): Sheer Cold ----------------------------------
    async def test_vanillish_sheer_cold_locks_next_turn_only(self):
        t = self.table()
        v = self.mine(t, VANILLISH, W, 3)
        v.set_attribute(AttrID.HP, 400)
        title, _ = self.filler_attack()
        t.energy(self.opp, W, 5)
        await t.attack(v, 'Sheer Cold')
        self.assertEqual(400 - t.hp(self.opp), 60)
        t.next_turn()
        self.assertIsNone(t.attack_offer(self.opp, title, pid=P2))
        t.next_turn()
        t.next_turn()
        self.assertIsNotNone(t.attack_offer(self.opp, title, pid=P2))

    # --- N's Vanilluxe (ASC 51): Snow Coating / Blizzard -----------------------
    async def test_vanilluxe_snow_coating_doubles_opponent_counters_only(self):
        t = self.table()
        self.hurt(t, self.opp, 30)
        ob1 = self.hurt(t, self.neutral(t.put(self.filler, P2, 'bench')), 10)
        ob2 = self.neutral(t.put(self.filler, P2, 'bench'))
        mb = self.hurt(t, self.neutral(t.put(self.filler, P1, 'bench')), 10)
        v = self.mine(t, VANILLUXE, W, 2)
        await t.attack(v, 'Snow Coating')
        self.assertEqual(t.damage(self.opp), 60)
        self.assertEqual(t.damage(ob1), 20)
        self.assertEqual(t.damage(ob2), 0)
        self.assertEqual(t.damage(mb), 10)

    async def test_vanilluxe_blizzard_spreads_to_opponent_bench_only(self):
        t = self.table()
        ob = self.neutral(t.put(self.filler, P2, 'bench'))
        mb = self.neutral(t.put(self.filler, P1, 'bench'))
        v = self.mine(t, VANILLUXE, W, 3)
        await t.attack(v, 'Blizzard')
        self.assertEqual(400 - t.hp(self.opp), 120)
        self.assertEqual(t.damage(ob), 10)
        self.assertEqual(t.damage(mb), 0)

    # --- Accelgor (FST 14): Ninja Tornado -------------------------------------
    async def test_accelgor_ninja_tornado_for_grass_after_moving_up(self):
        t = self.table()
        self.mine(t, self.filler)
        a = self.mine(t, ACCELGOR, G, 1, zone='bench')
        sw = t.put(SWITCH, P1, 'hand')
        t.pokemon = lambda cands, prompt: a if a in cands else cands[0]
        await t.play(sw, targets=[a.entity_id])
        self.assertIs(t.active(P1), a)
        self.assertIsNotNone(t.attack_offer(a, 'Ninja Tornado'))
        await t.attack(a, 'Ninja Tornado')
        self.assertEqual(400 - t.hp(self.opp), 120)

    async def test_accelgor_ninja_tornado_full_cost_if_already_active(self):
        t = self.table()
        a = self.mine(t, ACCELGOR, G, 1)
        self.assertIsNone(t.attack_offer(a, 'Ninja Tornado'))
        t.energy(a, W, 2)
        self.assertIsNotNone(t.attack_offer(a, 'Ninja Tornado'))

    # --- Lilligant (JTG 7): Sunny Day / Tapu Bulu (SFA 6): Wood Hammer --------
    async def test_lilligant_sunny_day_boosts_grass_and_fire_from_bench(self):
        cases = ((TAPU_BULU, G, 4, 'Wood Hammer', 240),
                 (CHARCADET, R, 1, 'Ember', 50),
                 (self.filler, W, 4, None, None))
        for spec, kind, n, title, expect in cases:
            with self.subTest(spec=str(spec)):
                t = self.table()
                attacker = self.mine(t, spec, kind, n)
                attacker.set_attribute(AttrID.HP, 400)
                self.mine(t, LILLIGANT, zone='bench')
                if title is None:
                    title, base = None, None
                    for a in def_for(attacker.archetype_id).abilities:
                        if isinstance(a, Attack) and a.damage and not a.game_text:
                            title, base = a.title, a.damage
                            break
                    expect = base
                await t.attack(attacker, title)
                self.assertEqual(400 - t.hp(self.opp), expect)

    async def test_lilligant_sunny_day_not_bench_damage_or_opponents_lilligant(self):
        # opponent's Lilligant does not boost my Grass attack
        t = self.table()
        bulu = self.mine(t, TAPU_BULU, G, 4)
        bulu.set_attribute(AttrID.HP, 400)
        t.put(LILLIGANT, P2, 'bench')
        await t.attack(bulu, 'Wood Hammer')
        self.assertEqual(400 - t.hp(self.opp), 220)
        self.assertEqual(400 - t.hp(bulu), 30)      # Wood Hammer recoil (Tapu Bulu)
        # my Lilligant: bench damage from a Grass attack is not boosted
        t = self.table()
        h = self.mine(t, HIPPOWDON, F, 3)
        h.set_attribute(AttrID.POKEMON_TYPES, [G.value])
        self.mine(t, LILLIGANT, zone='bench')
        ob = self.hurt(t, self.neutral(t.put(self.filler, P2, 'bench')), 10)
        await t.attack(h, 'Super Sandstorm')
        self.assertEqual(400 - t.hp(self.opp), 170)
        self.assertEqual(t.damage(ob), 50)

    # --- Spell Tag (LOT 190) --------------------------------------------------
    async def _spell_tag(self, spec):
        t = self.table()
        victim = self.mine(t, spec, P, 1)
        tag = t.put(SPELL_TAG, P1, 'hand')
        await t.play(tag, targets=[victim.entity_id])
        self.assertIn(tag, t.attached(victim))
        victim.set_attribute(AttrID.HP, 10)
        self.mine(t, self.filler, zone='bench')
        calls = []

        async def place(player_id, source_id, pool, count, prompt=''):
            calls.append(count)
            return {self.opp.entity_id: count}
        with patch.object(t.session, 'prompt_damage_counter_placement', place):
            dmg = await self.opp_hits(t)
        self.assertNotIn(victim, t.zone(P1, 'active'))
        return t, calls, dmg

    async def test_spell_tag_psychic_ko_places_four_counters(self):
        t, calls, _ = await self._spell_tag(DRIFLOON)
        self.assertEqual(calls, [4])
        self.assertEqual(400 - t.hp(self.opp), 40)

    async def test_spell_tag_non_psychic_ko_does_nothing(self):
        t, calls, _ = await self._spell_tag(CHARCADET)      # Fire, no Ability
        self.assertEqual(calls, [])
        self.assertEqual(t.hp(self.opp), 400)

    # --- Togetic (OBF 84): Shared Peace ---------------------------------------
    async def test_togetic_shared_peace_each_player_draws_three(self):
        t = self.table()
        tg = self.mine(t, TOGETIC, W, 1)
        t.put(self.item, P2, 'hand')
        await t.attack(tg, 'Shared Peace')
        self.assertEqual(len(t.zone(P1, 'hand')), 3)
        self.assertEqual(len(t.zone(P2, 'hand')), 4)

    # --- Slowbro (PGO 20) -------------------------------------------------------
    async def test_slowbro_tumbling_tackle_both_asleep(self):
        t = self.table()
        s = self.mine(t, SLOWBRO, W, 1)
        await t.attack(s, 'Tumbling Tackle')
        self.assertIn(ASLEEP, t.conditions(s))
        self.assertIn(ASLEEP, t.conditions(self.opp))
        self.assertEqual(400 - t.hp(self.opp), 20)

    async def test_slowbro_twilight_inspiration_exactly_one_prize(self):
        for opp_prizes in (2, 0):
            t = self.table()
            s = self.mine(t, SLOWBRO, W, 2)
            t.set_prizes(P2, opp_prizes)
            with self.subTest(opp_prizes=opp_prizes):
                self.assertIsNone(t.attack_offer(s, 'Twilight Inspiration'))
        t = self.table()
        s = self.mine(t, SLOWBRO, W, 2)
        t.set_prizes(P2, 1)
        self.assertIsNotNone(t.attack_offer(s, 'Twilight Inspiration'))
        await t.attack(s, 'Twilight Inspiration')
        self.assertEqual(len(t.zone(P1, 'prizes')), 4)
        self.assertEqual(len(t.zone(P2, 'prizes')), 1)
        self.assertEqual(t.hp(self.opp), 400)

    # --- Starmie (MEW 121): Mysterious Comet ------------------------------------
    # BUG: Mysterious Comet places the counters but Starmie and its cards stay in play
    async def test_starmie_mysterious_comet_two_counters_then_discards_itself(self):
        t = self.table()
        self.mine(t, self.filler)
        st = self.mine(t, STARMIE, W, 1, zone='bench')
        attached = list(t.attached(st))
        ob = self.neutral(t.put(self.filler, P2, 'bench'))
        t.pokemon = lambda cands, prompt: ob if ob in cands else cands[0]
        t.picks = lambda cards, count, prompt, display: [c for c in cards if c is ob][:count] or cards[:count]
        await t.use(st, 'Mysterious Comet')
        self.assertEqual(t.damage(ob), 20)
        self.assertEqual(t.hp(self.opp), 400)
        discard = t.zone(P1, 'discard')
        self.assertIn(st, discard)
        for c in attached:
            self.assertIn(c, discard)

    async def test_starmie_mysterious_comet_blocked_by_ability_lock(self):
        t = Table(self)
        self.opp = self.neutral(t.put(WEEZING, P2, 'active'), 400)
        st = self.mine(t, STARMIE, W, 1, zone='active')
        self.assertIsNone(t.ability_offer(st, 'Mysterious Comet'))

    # --- Professor Sada's Vitality (PAR 170) --------------------------------------
    # BUG: Sada attaches only 1 Energy and may pick a non-Ancient Pokémon
    async def test_sada_attaches_to_ancient_only_and_draws_three(self):
        t = self.table()
        tusk = self.mine(t, GREAT_TUSK)
        mane = self.mine(t, FLUTTER_MANE, zone='bench')
        plain = self.mine(t, self.filler, zone='bench')
        e1 = t.put(t.basic_energy(F), P1, 'discard')
        e2 = t.put(t.basic_energy(P), P1, 'discard')
        sada = t.put(SADA, P1, 'hand')
        seen = []

        def pick_mon(cands, prompt):
            seen.append(list(cands))
            return cands[0]
        t.pokemon = pick_mon
        await t.play(sada)
        energies = set(e.entity_id for e in (e1, e2))
        self.assertEqual(sum(1 for c in t.attached(tusk) if c.entity_id in energies), 1)
        self.assertEqual(sum(1 for c in t.attached(mane) if c.entity_id in energies), 1)
        self.assertFalse(any(c.entity_id in energies for c in t.attached(plain)))
        for cands in seen:
            self.assertNotIn(plain, cands)
        self.assertEqual(len(t.zone(P1, 'hand')), 3)

    # BUG: with no Ancient Pokémon, Sada attaches to a non-Ancient and draws 3
    async def test_sada_no_ancient_no_energy_no_draw(self):
        t = self.table()
        self.mine(t, self.filler)
        t.put(t.basic_energy(F), P1, 'discard')
        sada = t.put(SADA, P1, 'hand')
        if t.can(sada, 'UseTrainerCard'):
            await t.play(sada)
            self.assertEqual(len(t.zone(P1, 'hand')), 0)

    # --- Porygon (PAR 142): Data Displacement -------------------------------------
    async def test_porygon_data_displacement_moves_energy_on_heads(self):
        for heads in (True, False):
            t = self.table()
            e = t.energy(self.opp, W, 1)
            ob = self.neutral(t.put(self.filler, P2, 'bench'))
            pg = self.mine(t, PORYGON, W, 1)
            t.heads = heads
            await t.attack(pg, 'Data Displacement')
            with self.subTest(heads=heads):
                self.assertEqual(400 - t.hp(self.opp), 10)
                self.assertEqual(e in t.attached(ob), heads)
                self.assertEqual(e in t.attached(self.opp), not heads)

    # --- Hippopotas (BKT 83): Nose Jet ---------------------------------------------
    async def test_hippopotas_nose_jet_tails_attack_does_nothing(self):
        for heads in (True, False):
            t = self.table()
            hp = self.mine(t, HIPPOPOTAS, F, 3)
            hp.set_attribute(AttrID.HP, 400)
            await t.attack(hp, 'Nose Jet')
            self.assertEqual(400 - t.hp(self.opp), 30)
            with patch.object(t.session, '_attack_attempt_coins',
                              lambda pid, n: [heads] * n):
                dmg = await self.opp_hits(t)
            with self.subTest(heads=heads):
                self.assertEqual(400 - t.hp(hp), dmg if heads else 0)

    async def test_hippopotas_nose_jet_expires_after_one_turn(self):
        t = self.table()
        hp = self.mine(t, HIPPOPOTAS, F, 3)
        hp.set_attribute(AttrID.HP, 400)
        await t.attack(hp, 'Nose Jet')
        t.next_turn()
        t.next_turn()
        calls = []

        def coins(pid, n):
            calls.append(n)
            return [False] * n
        with patch.object(t.session, '_attack_attempt_coins', coins):
            dmg = await self.opp_hits(t)
        self.assertEqual(calls, [])
        self.assertEqual(400 - t.hp(hp), dmg)

    # --- Burning Energy (BKT 151) ----------------------------------------------------
    async def test_burning_energy_only_fire_targets(self):
        t = self.table()
        plain = self.mine(t, self.filler)
        fire = self.mine(t, CHARCADET, zone='bench')
        be = t.put(BURNING, P1, 'hand')
        targets = t.targets(be, 'DefaultEnergyPlayAbility')
        self.assertIn(fire.entity_id, targets)
        self.assertNotIn(plain.entity_id, targets)

    async def test_burning_energy_returns_after_own_attack_discards_it(self):
        t = self.table()
        ch = self.mine(t, CHARCADET)
        be = t.put(BURNING, P1, 'hand')
        await t.play(be, targets=[ch.entity_id])
        self.assertIn(be, t.attached(ch))
        self.assertIsNotNone(t.attack_offer(ch, 'Ember'))
        await t.attack(ch, 'Ember')
        self.assertEqual(400 - t.hp(self.opp), 30)
        self.assertIn(be, t.attached(ch))
        self.assertNotIn(be, t.zone(P1, 'discard'))


if __name__ == '__main__':
    unittest.main()
