"""Bug hunt round 7, chunk 18: Fennekin (CRI 11 / SIT 25), Braixen (FCO 12 /
SIT 26), Pidove, Unfezant, Diggersby, Espurr (FLI 44 / CRI 36 / SSP 84),
Team Rocket's Factory, Victini, Joltik, Meowstic, Duskull -- each checked
against its printed text, including the cases where it should NOT work.

Note: the chunk listed SIT 25/26 as XY8 printings; SIT is SWSH12, so the
SWSH12 Fennekin_25 / Braixen_26 scripts are the ones tested here."""
import unittest
from unittest.mock import patch

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table, CONFUSED
from spirit.game.attributes import AttrID, PokemonTypes
from spirit.game.data_utils import Attack, def_for
from spirit.game.session.effects import EffectContext
from spirit.tools.effect_smoke import P1, P2

FIRE, WATER, PSY = PokemonTypes.FIRE, PokemonTypes.WATER, PokemonTypes.PSYCHIC
GRASS = PokemonTypes.GRASS

FENNEKIN_CRI, FENNEKIN_SIT = 'ME4.Fennekin_11', 'SWSH12.Fennekin_25'
BRAIXEN_FCO, BRAIXEN_SIT = 'XY10.Braixen_12', 'SWSH12.Braixen_26'
PIDOVE, UNFEZANT = 'SV05.Pidove_133', 'SV05.Unfezant_135'
DIGGERSBY = 'ME3.Diggersby_65'
ESPURR_FLI, ESPURR_CRI, ESPURR_SSP = 'SM6.Espurr_44', 'ME4.Espurr_36', 'SV08.Espurr_84'
FACTORY = 'SV10.TeamRocketsFactory_173'
PETREL = 'SV10.TeamRocketsPetrel_176'
TR_GREAT_BALL = 'SV10.TeamRocketsGreatBall_175'
VICTINI = 'ZSV10PT5.Victini_12'
JOLTIK = 'SV065.Joltik_1'
MEOWSTIC = 'ME3.Meowstic_34'
EMMA = 'ME4.Emma_77'
SERENA = 'SWSH12.Serena_164'


class Chunk18(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    def table(self):
        t = Table(self)
        self.opp = t.put(self.filler, P2, 'active')
        self.opp.set_attribute(AttrID.HP, 400)
        self.opp.set_attribute(AttrID.WEAKNESS_TYPES, [])
        self.opp.set_attribute(AttrID.RESISTANCE_TYPES, [])
        return t

    def mine(self, t, spec, kind=None, count=0, zone='active', pid=P1):
        p = t.put(spec, pid, zone)
        p.set_attribute(AttrID.WEAKNESS_TYPES, [])
        p.set_attribute(AttrID.RESISTANCE_TYPES, [])
        if count:
            t.energy(p, kind, count)
        return p

    def clear_hand(self, t, pid=P1):
        area = t.board.find_player_area(pid, 'hand')
        for c in list(area.children):
            area.remove_child(c)

    def is_energy(self, card):
        return card.archetype_id.lower() in {g.lower() for g in self.energies.values()}

    def energies_on(self, pokemon):
        return [c for c in pokemon.children if self.is_energy(c)]

    def dealt(self):
        return 400 - self.opp.get_attribute(AttrID.HP)

    def is_card(self, card, spec):
        return card.archetype_id.lower() == fixtures.definition(spec).guid.lower()

    def filler_attack(self):
        for a in def_for(self.opp.archetype_id).abilities:
            if isinstance(a, Attack) and a.damage:
                return a.title
        raise AssertionError('filler has no damaging attack')

    # --- Fennekin CRI 11: Call for Family ------------------------------------
    async def test_fennekin_cri_call_for_family_benches_two_basics_only(self):
        t = self.table()
        fen = self.mine(t, FENNEKIN_CRI, WATER, 1)
        t.deck(P1, [PIDOVE, JOLTIK, BRAIXEN_FCO, PIDOVE])
        await t.attack(fen, 'Call for Family')
        bench = t.zone(P1, 'bench')
        self.assertEqual(len(bench), 2)
        self.assertTrue(all(def_for(c.archetype_id).display_name in ('Pidove', 'Joltik')
                            for c in bench))

    async def test_fennekin_cri_call_for_family_respects_bench_space(self):
        t = self.table()
        fen = self.mine(t, FENNEKIN_CRI, WATER, 1)
        for _ in range(4):
            self.mine(t, self.filler, zone='bench')
        t.deck(P1, [PIDOVE, JOLTIK, PIDOVE])
        await t.attack(fen, 'Call for Family')
        self.assertEqual(len(t.zone(P1, 'bench')), 5)

    # --- Braixen FCO 12: Destructive Flame -----------------------------------
    async def test_braixen_fco_destructive_flame_heads_discards_energy(self):
        t = self.table()
        brx = self.mine(t, BRAIXEN_FCO, FIRE, 1)
        t.energy(self.opp, WATER, 2)
        t.heads = True
        await t.attack(brx, 'Destructive Flame')
        self.assertEqual(self.dealt(), 20)
        self.assertEqual(len(self.energies_on(self.opp)), 1)
        self.assertEqual(len(self.energies_on(brx)), 1)

    async def test_braixen_fco_destructive_flame_tails_keeps_energy(self):
        t = self.table()
        brx = self.mine(t, BRAIXEN_FCO, FIRE, 1)
        t.energy(self.opp, WATER, 2)
        t.heads = False
        await t.attack(brx, 'Destructive Flame')
        self.assertEqual(self.dealt(), 20)
        self.assertEqual(len(self.energies_on(self.opp)), 2)

    # --- Pidove TEF 133: Emergency Evolution ---------------------------------
    async def test_pidove_emergency_evolution_at_30_hp(self):
        t = self.table()
        pidove = self.mine(t, PIDOVE, zone='bench', )
        self.mine(t, self.filler)
        pidove.set_attribute(AttrID.HP, 30)
        t.deck(P1, [UNFEZANT])
        self.assertIsNotNone(t.ability_offer(pidove, 'Emergency Evolution'))
        await t.use(pidove, 'Emergency Evolution')
        bench = t.zone(P1, 'bench')
        self.assertEqual(len(bench), 1)
        self.assertEqual(def_for(bench[0].archetype_id).display_name, 'Unfezant')
        self.assertEqual(t.damage(bench[0]), 20)
        self.assertFalse(any(self.is_card(c, UNFEZANT) for c in t.zone(P1, 'deck')))

    # BUG: Emergency Evolution is offered (and evolves) above 30 remaining HP;
    # standard_ability_condition has no "remaining HP is N or less" gate.
    async def test_pidove_emergency_evolution_not_above_30_hp(self):
        t = self.table()
        pidove = self.mine(t, PIDOVE)
        pidove.set_attribute(AttrID.HP, 40)
        t.deck(P1, [UNFEZANT])
        offer = t.ability_offer(pidove, 'Emergency Evolution')
        if offer is not None:
            await t.do(offer)
        self.assertIs(t.active(P1), pidove)
        self.assertIsNone(offer)

    # --- Unfezant TEF 135 ------------------------------------------------------
    async def test_unfezant_opposing_winds_returns_two_energy_to_hand(self):
        t = self.table()
        unf = self.mine(t, UNFEZANT, WATER, 2)
        t.energy(self.opp, WATER, 3)
        before = len(t.zone(P2, 'hand'))
        t.yes = True
        await t.attack(unf, 'Opposing Winds')
        self.assertEqual(self.dealt(), 70)
        self.assertEqual(len(self.energies_on(self.opp)), 1)
        self.assertEqual(len(t.zone(P2, 'hand')), before + 2)

    async def test_unfezant_opposing_winds_is_optional(self):
        t = self.table()
        unf = self.mine(t, UNFEZANT, WATER, 2)
        t.energy(self.opp, WATER, 3)
        t.yes = False
        t.picks = lambda cards, count, prompt, display: []
        await t.attack(unf, 'Opposing Winds')
        self.assertEqual(self.dealt(), 70)
        self.assertEqual(len(self.energies_on(self.opp)), 3)

    async def test_unfezant_boundless_power_locks_next_turn_only(self):
        t = self.table()
        unf = self.mine(t, UNFEZANT, WATER, 3)
        await t.attack(unf, 'Boundless Power')
        self.assertEqual(self.dealt(), 180)
        t.next_turn()
        t.next_turn()
        self.assertIsNone(t.attack_offer(unf, 'Boundless Power'))
        self.assertIsNone(t.attack_offer(unf, 'Opposing Winds'))
        t.next_turn()
        t.next_turn()
        self.assertIsNotNone(t.attack_offer(unf, 'Boundless Power'))

    # --- Diggersby POR 65: Earthquake -----------------------------------------
    async def test_diggersby_earthquake_hits_own_bench_not_opponents(self):
        t = self.table()
        dig = self.mine(t, DIGGERSBY, WATER, 1)
        mine_b = self.mine(t, self.filler, zone='bench')
        opp_b = self.mine(t, self.filler, zone='bench', pid=P2)
        await t.attack(dig, 'Earthquake')
        self.assertEqual(self.dealt(), 140)
        self.assertEqual(t.damage(mine_b), 30)
        self.assertEqual(t.damage(opp_b), 0)
        self.assertEqual(t.damage(dig), 0)

    # --- Espurr FLI 44: Energy Teaser -----------------------------------------
    async def test_espurr_fli_energy_teaser_moves_from_opp_bench(self):
        t = self.table()
        esp = self.mine(t, ESPURR_FLI, PSY, 1)
        src = self.mine(t, self.filler, zone='bench', pid=P2)
        dst = self.mine(t, self.filler, zone='bench', pid=P2)
        t.energy(src, WATER, 1)
        t.pokemon = lambda cands, prompt: (src if src in cands else
                                           (dst if dst in cands else cands[0]))
        await t.attack(esp, 'Energy Teaser')
        self.assertEqual(len(self.energies_on(src)), 0)
        self.assertEqual(len(self.energies_on(dst)) + len(self.energies_on(self.opp)), 1)
        self.assertEqual(self.dealt(), 0)

    async def test_espurr_fli_energy_teaser_ignores_opp_active_energy(self):
        t = self.table()
        esp = self.mine(t, ESPURR_FLI, PSY, 1)
        bench = self.mine(t, self.filler, zone='bench', pid=P2)
        t.energy(self.opp, WATER, 1)
        await t.attack(esp, 'Energy Teaser')
        self.assertEqual(len(self.energies_on(self.opp)), 1)
        self.assertEqual(len(self.energies_on(bench)), 0)

    # --- Braixen SIT 26: Flare Parade -----------------------------------------
    async def test_braixen_sit_flare_parade_counts_serena(self):
        t = self.table()
        brx = self.mine(t, BRAIXEN_SIT, WATER, 2)
        t.put(SERENA, P1, 'discard')
        t.put(SERENA, P1, 'discard')
        t.put(EMMA, P1, 'discard')
        t.put(SERENA, P2, 'discard')                    # opponent's: not counted
        await t.attack(brx, 'Flare Parade')
        self.assertEqual(self.dealt(), 120)

    async def test_braixen_sit_flare_parade_no_serena_no_damage(self):
        t = self.table()
        brx = self.mine(t, BRAIXEN_SIT, WATER, 2)
        t.put(EMMA, P1, 'discard')
        await t.attack(brx, 'Flare Parade')
        self.assertEqual(self.dealt(), 0)

    # --- Fennekin SIT 25: Lead ------------------------------------------------
    async def test_fennekin_sit_lead_finds_supporter(self):
        t = self.table()
        fen = self.mine(t, FENNEKIN_SIT, WATER, 1)
        self.clear_hand(t)
        t.deck(P1, [EMMA])
        await t.attack(fen, 'Lead')
        hand = t.zone(P1, 'hand')
        self.assertEqual(len(hand), 1)
        self.assertTrue(self.is_card(hand[0], EMMA))

    async def test_fennekin_sit_lead_only_supporters(self):
        t = self.table()
        fen = self.mine(t, FENNEKIN_SIT, WATER, 1)
        self.clear_hand(t)
        t.deck(P1, [TR_GREAT_BALL, PIDOVE])
        await t.attack(fen, 'Lead')
        self.assertEqual(t.zone(P1, 'hand'), [])

    # --- Team Rocket's Factory DRI 173 ----------------------------------------
    async def test_factory_after_team_rocket_supporter_draws_two_once(self):
        t = self.table()
        self.mine(t, self.filler)
        stadium = t.stadium(FACTORY, P2)
        self.assertEqual(t.offers(stadium, None, P1), [])
        self.clear_hand(t)
        petrel = t.put(PETREL, P1, 'hand')
        await t.play(petrel)
        n = len(t.zone(P1, 'hand'))
        offers = t.offers(stadium, None, P1)
        self.assertTrue(offers)
        await t.do(offers[0])
        self.assertEqual(len(t.zone(P1, 'hand')), n + 2)
        self.assertEqual(t.offers(stadium, None, P1), [])          # once per turn
        # next turn (opponent): no TR Supporter played yet -> not offered
        t.next_turn()
        self.assertEqual(t.offers(stadium, None, P2), [])

    async def test_factory_not_after_other_supporter_or_tr_item(self):
        t = self.table()
        self.mine(t, self.filler)
        stadium = t.stadium(FACTORY, P1)
        self.mine(t, PIDOVE, zone='bench')
        great_ball = t.put(TR_GREAT_BALL, P1, 'hand')
        if t.can(great_ball, 'UseTrainerCard'):
            await t.play(great_ball)
        emma = t.put(EMMA, P1, 'hand')
        t.put(self.filler, P2, 'hand')
        await t.play(emma)
        self.assertEqual(t.offers(stadium, None, P1), [])

    # --- Victini BLK 12: V-Force ----------------------------------------------
    # BUG: V-Force does 120 with only 4 Benched Pokémon; bw_legacy_attack has
    # no "if you have N or fewer Benched Pokémon, this attack does nothing" branch.
    async def test_victini_v_force_needs_five_benched(self):
        t = self.table()
        vic = self.mine(t, VICTINI, FIRE, 2)
        for _ in range(4):
            self.mine(t, self.filler, zone='bench')
        await t.attack(vic, 'V-Force')
        self.assertEqual(self.dealt(), 0)

    async def test_victini_v_force_full_bench_hits(self):
        t = self.table()
        vic = self.mine(t, VICTINI, FIRE, 2)
        for _ in range(5):
            self.mine(t, self.filler, zone='bench')
        await t.attack(vic, 'V-Force')
        self.assertEqual(self.dealt(), 120)

    # --- Joltik SFA 1: Splashing Dodge ----------------------------------------
    async def _joltik_then_opponent_attacks(self, heads):
        t = self.table()
        jol = self.mine(t, JOLTIK, GRASS, 1)
        self.mine(t, self.filler, zone='bench')            # so a KO doesn't end the game
        t.energy(self.opp, WATER, 4)
        t.heads = heads
        await t.attack(jol, 'Splashing Dodge')
        self.assertEqual(self.dealt(), 10)
        t.next_turn()
        title = self.filler_attack()
        await t.attack(self.opp, title, pid=P2)
        return t, jol

    async def test_joltik_splashing_dodge_heads_prevents_damage(self):
        t, jol = await self._joltik_then_opponent_attacks(True)
        self.assertIs(t.active(P1), jol)
        self.assertEqual(t.damage(jol), 0)

    async def test_joltik_splashing_dodge_tails_no_protection(self):
        t, jol = await self._joltik_then_opponent_attacks(False)
        self.assertTrue(t.active(P1) is not jol or t.damage(jol) > 0)

    # --- Espurr CRI 36: Buddy Attack ------------------------------------------
    async def test_espurr_cri_buddy_attack_with_emma(self):
        t = self.table()
        esp = self.mine(t, ESPURR_CRI, PSY, 1)
        t.put(self.filler, P2, 'hand')
        emma = t.put(EMMA, P1, 'hand')
        await t.play(emma)
        await t.attack(esp, 'Buddy Attack')
        self.assertEqual(self.dealt(), 70)

    async def test_espurr_cri_buddy_attack_without_emma(self):
        t = self.table()
        esp = self.mine(t, ESPURR_CRI, PSY, 1)
        petrel = t.put(PETREL, P1, 'hand')                 # other Supporter
        await t.play(petrel)
        await t.attack(esp, 'Buddy Attack')
        self.assertEqual(self.dealt(), 10)

    # --- Meowstic POR 34 -------------------------------------------------------
    async def test_meowstic_perplex_confuses(self):
        t = self.table()
        meo = self.mine(t, MEOWSTIC, PSY, 1)
        await t.attack(meo, 'Perplex')
        self.assertIn(CONFUSED, t.conditions(self.opp))
        self.assertEqual(self.dealt(), 0)

    async def test_meowstic_psychic_counts_defender_energy(self):
        t = self.table()
        meo = self.mine(t, MEOWSTIC, PSY, 3)                # own energy doesn't count
        t.energy(self.opp, WATER, 2)
        await t.attack(meo, 'Psychic')
        self.assertEqual(self.dealt(), 90)

    async def test_meowstic_psychic_no_defender_energy(self):
        t = self.table()
        meo = self.mine(t, MEOWSTIC, PSY, 1)
        bench = self.mine(t, self.filler, zone='bench', pid=P2)
        t.energy(bench, WATER, 2)                           # benched energy doesn't count
        await t.attack(meo, 'Psychic')
        self.assertEqual(self.dealt(), 30)

    # --- Espurr SSP 84: See Through -------------------------------------------
    async def test_espurr_ssp_see_through_reveals_opponent_hand(self):
        t = self.table()
        esp = self.mine(t, ESPURR_SSP, WATER, 1)
        t.put(self.filler, P2, 'hand')
        calls = []
        original = EffectContext.reveal_hand

        async def spy(ctx, of_player=None, *a, **k):
            calls.append(of_player)
            return await original(ctx, of_player, *a, **k)

        before = (len(t.zone(P1, 'hand')), len(t.zone(P2, 'hand')))
        with patch.object(EffectContext, 'reveal_hand', spy):
            await t.attack(esp, 'See Through')
        self.assertEqual(calls, [P2])
        self.assertEqual((len(t.zone(P1, 'hand')), len(t.zone(P2, 'hand'))), before)
        self.assertEqual(self.dealt(), 0)


if __name__ == '__main__':
    unittest.main()
