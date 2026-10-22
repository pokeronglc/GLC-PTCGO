"""Bug hunt round 7, chunk 36: Magmar, Magmortar, Burning Scarf, Kecleon,
Supereffective Glasses, Talonflame, Dan, Chinchou, Emolga, Team Rocket's
Larvitar / Pupitar / Tyranitar, Dewpider, Shieldon, Bastiodon -- each checked
against its printed text, including the cases where it should NOT work.

Path corrections: Kecleon CRE 122 is SWSH6 (chunk said SV09), Chinchou SUM 49
is SM1 (chunk said SM7, which is the CES printing)."""
import random
import unittest
from unittest.mock import patch

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table, BURNED
from spirit.game.attributes import AttrID, PokemonTypes
from spirit.game.data_utils import def_for
from spirit.game.session.passives import effective_pokemon_types
from spirit.tools.effect_smoke import P1, P2

FIRE, WATER, FIGHT, GRASS, METAL, LIGHT = (
    PokemonTypes.FIRE, PokemonTypes.WATER, PokemonTypes.FIGHTING,
    PokemonTypes.GRASS, PokemonTypes.METAL, PokemonTypes.LIGHTNING)

MAGMAR = 'SM11.Magmar_21'
MAGMORTAR = 'SV09.Magmortar_21'
SCARF = 'SWSH2.BurningScarf_155'
KECLEON = 'SWSH6.Kecleon_122'
GLASSES = 'SWSH10.SupereffectiveGlasses_152'
TALONFLAME = 'XY11.Talonflame_96'
DAN = 'SWSH2.Dan_158'
CHINCHOU = 'SM1.Chinchou_49'
EMOLGA = 'SWSH12.Emolga_54'
LARVITAR = 'SV10.TeamRocketsLarvitar_94'
PUPITAR = 'SV10.TeamRocketsPupitar_95'
TYRANITAR = 'SV10.TeamRocketsTyranitar_96'
PLAIN_TYRANITAR = 'SM7.Tyranitar_87'
DEWPIDER = 'SM6.Dewpider_32'
FOSSIL = 'ME5.AntiqueArmorFossil_72'
SHIELDON = 'ME5.Shieldon_61'
BASTIODON = 'ME5.Bastiodon_62'


def name(card):
    return def_for(card.archetype_id).display_name


def coins(value):
    """Patch session-level random coins (Checkup burn flip) to heads/tails."""
    real = random.choice

    def choice(seq):
        if list(seq) in ([0, 1], [True, False]):
            return seq[0] if value == 'heads' else seq[1]
        return real(seq)
    return patch.object(random, 'choice', choice)


class Chunk36(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    def neutral(self, p, hp=None):
        p.set_attribute(AttrID.WEAKNESS_TYPES, [])
        p.set_attribute(AttrID.RESISTANCE_TYPES, [])
        if hp is not None:
            p.set_attribute(AttrID.HP, hp)
        return p

    def table(self, opp_spec=None, hp=400):
        t = Table(self)
        self.opp = self.neutral(t.put(opp_spec or self.filler, P2, 'active'), hp)
        return t

    def mine(self, t, spec, kind=None, count=0, zone='active', hp=None, pid=P1):
        p = self.neutral(t.put(spec, pid, zone), hp)
        if count:
            t.energy(p, kind, count)
        return p

    def clear_hand(self, t, pid=P1):
        area = t.board.find_player_area(pid, 'hand')
        for c in list(area.children):
            area.remove_child(c)

    # --- Magmar UNM 21: Smoke Bomb --------------------------------------------
    async def _smoke_bomb(self, heads):
        t = self.table()
        me = self.mine(t, MAGMAR, FIRE, 1, hp=300)
        await t.attack(me, 'Smoke Bomb')
        self.assertEqual(400 - t.hp(self.opp), 10)
        t.energy(self.opp, WATER, 3)
        t.next_turn()
        with patch.object(t.session, '_attack_attempt_coins',
                          lambda pid, count: [heads] * count):
            await t.attack(self.opp, 'Heavy Impact', pid=P2)
        return t, me

    async def test_magmar_smoke_bomb_tails_attack_fails(self):
        t, me = await self._smoke_bomb(False)
        self.assertEqual(300 - t.hp(me), 0)

    async def test_magmar_smoke_bomb_heads_attack_happens(self):
        t, me = await self._smoke_bomb(True)
        self.assertGreater(300 - t.hp(me), 0)

    # --- Magmortar JTG 21: Magma Surge / Searing Flame ------------------------
    async def test_magmortar_magma_surge_adds_3_counters_to_burned(self):
        t = self.table()
        self.mine(t, MAGMORTAR, zone='bench')
        self.mine(t, self.filler, hp=300)
        self.opp.set_attribute(AttrID.SPECIAL_CONDITIONS, [BURNED])
        with coins('tails'):
            await t.checkup()
        self.assertEqual(400 - t.hp(self.opp), 20 + 30)

    async def test_magmortar_magma_surge_not_on_unburned_or_own(self):
        t = self.table()
        self.mine(t, MAGMORTAR, zone='bench')
        own = self.mine(t, self.filler, hp=300)
        own.set_attribute(AttrID.SPECIAL_CONDITIONS, [BURNED])
        with coins('tails'):
            await t.checkup()
        self.assertEqual(400 - t.hp(self.opp), 0)
        self.assertEqual(300 - t.hp(own), 20)   # plain Burn only

    async def test_magmortar_searing_flame_heads_burns(self):
        t = self.table()
        me = self.mine(t, MAGMORTAR, FIRE, 3)
        t.heads = True
        await t.attack(me, 'Searing Flame')
        self.assertEqual(400 - t.hp(self.opp), 90)
        self.assertIn(BURNED, t.conditions(self.opp))

    async def test_magmortar_searing_flame_tails_no_burn(self):
        t = self.table()
        me = self.mine(t, MAGMORTAR, FIRE, 3)
        t.heads = False
        await t.attack(me, 'Searing Flame')
        self.assertEqual(400 - t.hp(self.opp), 90)
        self.assertNotIn(BURNED, t.conditions(self.opp))

    # --- Burning Scarf RCL 155 ------------------------------------------------
    async def _scarf(self, holder_spec):
        t = self.table()
        me = self.mine(t, holder_spec, hp=300)
        scarf = t.put(SCARF, P1, 'hand')
        await t.play(scarf, targets=[me.entity_id])
        self.assertIn(scarf, me.children)
        t.energy(self.opp, WATER, 3)
        t.next_turn()
        await t.attack(self.opp, 'Heavy Impact', pid=P2)
        self.assertGreater(300 - t.hp(me), 0)
        return t

    async def test_burning_scarf_fire_active_burns_attacker(self):
        await self._scarf(MAGMAR)
        self.assertIn(BURNED, t_conditions(self.opp))

    async def test_burning_scarf_non_fire_holder_no_burn(self):
        await self._scarf(self.filler)
        self.assertNotIn(BURNED, t_conditions(self.opp))

    # --- Kecleon CRE 122: Chromashift -----------------------------------------
    async def test_kecleon_chromashift_takes_energy_types(self):
        t = self.table()
        k = self.mine(t, KECLEON, WATER, 1)
        t.energy(k, FIRE, 1)
        types = set(effective_pokemon_types(t.board, k))
        self.assertEqual(types, {WATER.value, FIRE.value})

    async def test_kecleon_chromashift_no_energy_stays_colorless(self):
        t = self.table()
        k = self.mine(t, KECLEON)
        types = set(effective_pokemon_types(t.board, k))
        self.assertEqual(types, {PokemonTypes.COLORLESS.value})

    async def test_kecleon_chromashift_hits_weakness(self):
        t = self.table()
        self.opp.set_attribute(AttrID.WEAKNESS_TYPES, [WATER.value])
        k = self.mine(t, KECLEON, WATER, 3)
        await t.attack(k, 'Spinning Attack')
        self.assertEqual(400 - t.hp(self.opp), 180)

    # --- Supereffective Glasses ASR 152 ---------------------------------------
    async def test_glasses_weakness_times_three(self):
        t = self.table()
        self.opp.set_attribute(AttrID.WEAKNESS_TYPES, [FIRE.value])
        me = self.mine(t, MAGMORTAR, FIRE, 3)
        g = t.put(GLASSES, P1, 'hand')
        await t.play(g, targets=[me.entity_id])
        t.heads = False
        await t.attack(me, 'Searing Flame')
        self.assertEqual(400 - t.hp(self.opp), 270)

    async def test_glasses_without_weakness_no_change(self):
        t = self.table()
        me = self.mine(t, MAGMORTAR, FIRE, 3)
        g = t.put(GLASSES, P1, 'hand')
        await t.play(g, targets=[me.entity_id])
        t.heads = False
        await t.attack(me, 'Searing Flame')
        self.assertEqual(400 - t.hp(self.opp), 90)

    async def test_glasses_not_on_opponents_attacks(self):
        """Glasses only boost the holder's attacks, not attacks against it."""
        t = self.table()
        me = self.mine(t, MAGMAR, hp=300)
        me.set_attribute(AttrID.WEAKNESS_TYPES, [PokemonTypes.COLORLESS.value])
        g = t.put(GLASSES, P1, 'hand')
        await t.play(g, targets=[me.entity_id])
        t.energy(self.opp, WATER, 3)
        t.next_turn()
        await t.attack(self.opp, 'Heavy Impact', pid=P2)
        base = next(a.damage for a in def_for(self.opp.archetype_id).abilities
                    if a.title == 'Heavy Impact')
        self.assertEqual(300 - t.hp(me), base * 2)

    # --- Talonflame STS 96: Gale Wings / Aero Blitz ---------------------------
    async def test_talonflame_aero_blitz_takes_two_cards(self):
        t = self.table()
        me = self.mine(t, TALONFLAME, WATER, 1)
        self.clear_hand(t)
        a, b = t.deck(P1, [self.filler, MAGMAR])
        t.picks = lambda cards, count, prompt, display: [a, b]
        await t.attack(me, 'Aero Blitz')
        self.assertEqual(400 - t.hp(self.opp), 40)
        hand = t.zone(P1, 'hand')
        self.assertIn(a, hand)
        self.assertIn(b, hand)
        self.assertEqual(len(hand), 2)

    async def test_talonflame_aero_blitz_may_take_zero(self):
        t = self.table()
        me = self.mine(t, TALONFLAME, WATER, 1)
        self.clear_hand(t)
        t.picks = lambda cards, count, prompt, display: []
        await t.attack(me, 'Aero Blitz')
        self.assertEqual(len(t.zone(P1, 'hand')), 0)
        self.assertEqual(400 - t.hp(self.opp), 40)

    async def test_talonflame_gale_wings_declared(self):
        self.assertTrue(getattr(fixtures.definition(TALONFLAME), 'setup_as_active', False))

    # --- Dan RCL 158 -----------------------------------------------------------
    async def test_dan_draws_two(self):
        t = self.table()
        self.mine(t, self.filler)
        self.clear_hand(t)
        dan = t.put(DAN, P1, 'hand')
        picks = iter([0, 1])       # Rock vs Paper: Dan's player loses

        async def rps(ctx, prompt, buttons, *a, **k):
            return next(picks)
        with patch('spirit.game.session.effects.EffectContext.choose', rps):
            await t.play(dan)
        self.assertNotIn(dan, t.zone(P1, 'hand'))
        self.assertEqual(len(t.zone(P1, 'hand')), 2)

    # --- Chinchou SUM 49: Searching Light --------------------------------------
    async def test_chinchou_searching_light_looks_at_prize_keeps_it(self):
        t = self.table()
        me = self.mine(t, CHINCHOU, WATER, 1)
        self.clear_hand(t)
        prizes = list(t.zone(P1, 'prizes'))
        await t.attack(me, 'Searching Light')
        self.assertTrue(any('Prize' in (p or '') for p in t.prompts), t.prompts)
        self.assertEqual(t.zone(P1, 'prizes'), prizes)
        self.assertEqual(len(t.zone(P1, 'hand')), 0)
        self.assertEqual(400 - t.hp(self.opp), 0)

    # --- Emolga SIT 54: Lucky Find ---------------------------------------------
    async def test_emolga_lucky_find_takes_item(self):
        t = self.table()
        me = self.mine(t, EMOLGA, WATER, 1)
        self.clear_hand(t)
        mon = t.deck(P1, [self.filler])[0]
        seen = []
        t.picks = lambda cards, count, prompt, display: (seen.extend(cards), cards[:1])[1]
        await t.attack(me, 'Lucky Find')
        self.assertNotIn(mon, seen)
        hand = t.zone(P1, 'hand')
        self.assertEqual(len(hand), 1)
        self.assertEqual(def_for(hand[0].archetype_id).guid, self.item.guid)

    # --- Team Rocket's Larvitar DRI 94: Mountain Munch -------------------------
    async def test_tr_larvitar_mountain_munch_discards_opp_top(self):
        t = self.table()
        me = self.mine(t, LARVITAR, WATER, 1)
        top = t.deck(P2, [self.filler])[0]
        mine_top = t.deck(P1, [self.filler])[0]
        deck_before = len(t.zone(P2, 'deck'))
        await t.attack(me, 'Mountain Munch')
        self.assertIn(top, t.zone(P2, 'discard'))
        self.assertEqual(len(t.zone(P2, 'deck')), deck_before - 1)
        self.assertIn(mine_top, t.zone(P1, 'deck'))
        self.assertEqual(400 - t.hp(self.opp), 10)

    # --- Team Rocket's Pupitar DRI 95: Explosive Ascension ---------------------
    async def test_tr_pupitar_evolves_from_deck(self):
        t = self.table()
        me = self.mine(t, PUPITAR, WATER, 1)
        ty = t.deck(P1, [TYRANITAR])[0]
        await t.attack(me, 'Explosive Ascension')
        self.assertEqual(400 - t.hp(self.opp), 30)
        active = t.active(P1)
        self.assertEqual(name(active), "Team Rocket's Tyranitar")
        self.assertNotIn(ty, t.zone(P1, 'deck'))

    async def test_tr_pupitar_cannot_evolve_into_plain_tyranitar(self):
        t = self.table()
        me = self.mine(t, PUPITAR, WATER, 1)
        plain = t.deck(P1, [PLAIN_TYRANITAR])[0]
        await t.attack(me, 'Explosive Ascension')
        self.assertIn(plain, t.zone(P1, 'deck'))
        self.assertEqual(name(t.active(P1)), "Team Rocket's Pupitar")

    # --- Team Rocket's Tyranitar DRI 96 ----------------------------------------
    async def test_tr_tyranitar_sand_stream_hits_opp_basics_when_active(self):
        t = self.table()
        self.mine(t, TYRANITAR)
        opp_bench = self.neutral(t.put(self.filler, P2, 'bench'), 300)
        opp_stage1 = self.neutral(t.put(PUPITAR, P2, 'bench'), 300)
        my_bench = self.mine(t, self.filler, zone='bench', hp=300)
        await t.checkup()
        self.assertEqual(400 - t.hp(self.opp), 20)
        self.assertEqual(300 - t.hp(opp_bench), 20)
        self.assertEqual(300 - t.hp(opp_stage1), 0)
        self.assertEqual(300 - t.hp(my_bench), 0)

    async def test_tr_tyranitar_sand_stream_not_from_bench(self):
        t = self.table()
        self.mine(t, self.filler)
        self.mine(t, TYRANITAR, zone='bench')
        await t.checkup()
        self.assertEqual(400 - t.hp(self.opp), 0)

    async def test_tr_tyranitar_demolition_tackle_discards_energy(self):
        t = self.table()
        me = self.mine(t, TYRANITAR, FIGHT, 4)
        e = t.energy(self.opp, WATER, 1)
        await t.attack(me, 'Demolition Tackle')
        self.assertEqual(400 - t.hp(self.opp), 180)
        self.assertIn(e, t.zone(P2, 'discard'))

    # --- Dewpider FLI 32: Spider Web -------------------------------------------
    async def test_dewpider_spider_web_blocks_retreat_next_turn(self):
        t = self.table()
        me = self.mine(t, DEWPIDER, WATER, 1)
        self.neutral(t.put(self.filler, P2, 'bench'))
        t.energy(self.opp, WATER, 4)
        await t.attack(me, 'Spider Web')
        t.next_turn()
        self.assertFalse(t.can(self.opp, 'RetreatPokemon', pid=P2)
                         or bool([e for e in t.actions(P2)
                                  if e['entityID'] == self.opp.entity_id
                                  and 'Retreat' in e['selectableAction']['description']]))

    async def test_dewpider_spider_web_control_retreat_allowed(self):
        """Control: without Spider Web the same Pokémon can retreat."""
        t = self.table()
        self.mine(t, DEWPIDER, WATER, 1)
        self.neutral(t.put(self.filler, P2, 'bench'))
        t.energy(self.opp, WATER, 4)
        t.next_turn()
        self.assertTrue([e for e in t.actions(P2)
                         if e['entityID'] == self.opp.entity_id
                         and 'Retreat' in e['selectableAction']['description']])

    # --- Shieldon PBL 61 -------------------------------------------------------
    async def test_shieldon_evolves_from_antique_armor_fossil(self):
        t = self.table()
        fossil = self.mine(t, FOSSIL)
        t.state.entered_play_turn[fossil.entity_id] = 1
        sh = t.put(SHIELDON, P1, 'hand')
        await t.play(sh, targets=[fossil.entity_id])
        self.assertEqual(name(t.active(P1)), 'Shieldon')

    async def test_shieldon_smithereen_smash_discards_energy(self):
        t = self.table()
        me = self.mine(t, SHIELDON, METAL, 2)
        e = t.energy(self.opp, WATER, 1)
        await t.attack(me, 'Smithereen Smash')
        self.assertEqual(400 - t.hp(self.opp), 50)
        self.assertIn(e, t.zone(P2, 'discard'))

    # --- Bastiodon PBL 62: Ancient Bulwark -------------------------------------
    async def _bulwark(self, energy):
        t = Table(self)
        self.mine(t, self.filler, hp=300)
        self.mine(t, BASTIODON, zone='bench', hp=300)
        lar = self.neutral(t.put(LARVITAR, P2, 'active'), 300)
        t.energy(lar, WATER, energy)
        t.next_turn()
        await t.attack(lar, 'Mountain Munch', pid=P2)
        return t, t.active(P1)

    async def test_bastiodon_bulwark_prevents_two_energy_attacker(self):
        t, target = await self._bulwark(2)
        self.assertEqual(300 - t.hp(target), 0)

    async def test_bastiodon_bulwark_lets_three_energy_attacker_through(self):
        t, target = await self._bulwark(3)
        self.assertEqual(300 - t.hp(target), 10)

    async def test_bastiodon_bulwark_off_when_active(self):
        t = Table(self)
        bast = self.mine(t, BASTIODON, hp=300)
        lar = self.neutral(t.put(LARVITAR, P2, 'active'), 300)
        t.energy(lar, WATER, 1)
        t.next_turn()
        await t.attack(lar, 'Mountain Munch', pid=P2)
        self.assertEqual(300 - t.hp(bast), 10)


def t_conditions(pokemon):
    return set(pokemon.get_attribute(AttrID.SPECIAL_CONDITIONS) or [])


if __name__ == '__main__':
    unittest.main()
