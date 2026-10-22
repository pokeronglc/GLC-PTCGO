"""Bug hunt round 3, list 2: Trainers, Tools, Stadium and Special Energy,
checked against their printed text, including the cases where they should
NOT work."""
import unittest
from unittest.mock import patch

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table, CONFUSED, POISONED
from spirit.game.attributes import AttrID, PokemonTypes
from spirit.game.data_utils import def_for
from spirit.game.session.effects import EffectContext
from spirit.tools.effect_smoke import P1, P2

G, W, P = PokemonTypes.GRASS, PokemonTypes.WATER, PokemonTypes.PSYCHIC
TOOL_JAMMER, FLOAT = 'SWSH5.ToolJammer_136', 'XY8.FloatStone_137'
ACEROLA, PENNY = 'SM3.Acerola_112', 'SV1.Penny_252'
AROMATIC = 'SWSH4.AromaticGrassEnergy_162'
TRICK_COIN, GLIMWOOD = 'XY4.TrickCoin_108', 'SWSH3.GlimwoodTangle_162'
EXEGGUTOR = 'BW9.Exeggutor_5'           # Stomp: 60, flip: heads +30
ODDISH, GLOOM = 'SV035.Oddish_43', 'SM10.Gloom_7'
MISDREAVUS = 'SM4.Misdreavus_39'        # Confuse Ray


class RealCoinTable(Table):
    """Table whose coin flips go through the real EffectContext.flip_coins
    (so Glimwood Tangle / Trick Coin re-flip prompts happen); the RNG is
    scripted through `self.rng` (True = heads)."""

    def __init__(self, test):
        super().__init__(test)
        self.rng = []

    def _patches(self):
        table = self
        kept = [p for p in super()._patches() if p.attribute != 'flip_coins']

        def choice(options):
            return 0 if table.rng.pop(0) else 1
        return kept + [patch('spirit.game.session.effects.random.choice', choice)]


class Bughunt3B2Trainers(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    def table(self, cls=Table):
        t = cls(self)
        self.opp = t.put(self.filler, P2, 'active')
        self.big(self.opp)
        return t

    @staticmethod
    def big(p, hp=400):
        p.set_attribute(AttrID.WEAKNESS_TYPES, [])
        p.set_attribute(AttrID.RESISTANCE_TYPES, [])
        p.set_attribute(AttrID.HP, hp)

    def new_opp_active(self, t, spec):
        old = t.active(P2)
        mon = t.put(spec, P2, 'bench')
        t.board.move_card(old.entity_id, t.board.find_player_area(P2, 'bench').entity_id)
        t.board.move_card(mon.entity_id, t.board.find_player_area(P2, 'activePokemonArea').entity_id)
        return mon

    # --- Tool Jammer (BST 136) ---------------------------------------------
    async def test_tool_jammer_active_cancels_opponent_active_tool(self):
        t = self.table()
        base = t.retreat(self.opp)
        self.assertGreater(base, 0)
        me = t.put(self.filler, P1, 'active')
        t.attach(FLOAT, self.opp)
        self.assertEqual(t.retreat(self.opp), 0)
        await t.play(t.put(TOOL_JAMMER, P1, 'hand'), targets=[me.entity_id])
        self.assertEqual(t.retreat(self.opp), base)

    async def test_tool_jammer_on_bench_or_vs_benched_tool_does_nothing(self):
        t = self.table()
        t.put(self.filler, P1, 'active')
        bench = t.put(self.filler, P1, 'bench')
        t.attach(TOOL_JAMMER, bench)
        t.attach(FLOAT, self.opp)
        self.assertEqual(t.retreat(self.opp), 0)        # Jammer holder benched
        t2 = self.table()
        me = t2.put(self.filler, P1, 'active')
        t2.attach(TOOL_JAMMER, me)
        opp_bench = t2.put(self.filler, P2, 'bench')
        t2.attach(FLOAT, opp_bench)
        self.assertEqual(t2.retreat(opp_bench), 0)      # only the opposing Active is jammed

    async def test_tool_jammer_does_not_cancel_my_own_tools(self):
        t = self.table()
        me = t.put(self.filler, P1, 'active')
        t.attach(TOOL_JAMMER, me)
        t.attach(FLOAT, me)
        self.assertEqual(t.retreat(me), 0)

    # --- Acerola (BUS 112) -------------------------------------------------
    async def test_acerola_picks_up_damaged_pokemon_with_attachments(self):
        t = self.table()
        t.put(self.filler, P1, 'active')
        hurt = t.put(ODDISH, P1, 'bench', hp=30)
        healthy = t.put(ODDISH, P1, 'bench')
        e = t.energy(hurt, G)
        seen = {}

        def pick(cands, prompt):
            seen['c'] = list(cands)
            return hurt
        t.pokemon = pick
        await t.play(t.put(ACEROLA, P1, 'hand'))
        hand = t.zone(P1, 'hand')
        self.assertIn(hurt, hand)
        self.assertIn(e, hand)
        self.assertIn(healthy, t.zone(P1, 'bench'))
        self.assertNotIn(healthy, seen.get('c', []))
        self.assertEqual(hurt.get_attribute(AttrID.HP, None) in (None, 60), True)

    async def test_acerola_not_playable_without_damaged_pokemon(self):
        t = self.table()
        t.put(self.filler, P1, 'active')
        t.put(ODDISH, P1, 'bench')
        hurt_opp = t.put(ODDISH, P2, 'bench', hp=10)     # opponent's damage doesn't count
        self.assertFalse(t.can(t.put(ACEROLA, P1, 'hand'), 'UseTrainerCard'))

    # --- Penny (SVI 252 = reprint of SVI 183) -------------------------------
    async def test_penny_picks_up_basic_with_attachments(self):
        t = self.table()
        t.put(self.filler, P1, 'active')
        odd = t.put(ODDISH, P1, 'bench', hp=10)
        e = t.energy(odd, G)
        t.pokemon = lambda c, p: odd if odd in c else c[0]
        await t.play(t.put(PENNY, P1, 'hand'))
        self.assertIn(odd, t.zone(P1, 'hand'))
        self.assertIn(e, t.zone(P1, 'hand'))

    async def test_penny_cannot_take_evolved_pokemon(self):
        t = self.table()
        t.put(self.filler, P1, 'active')
        odd = t.put(ODDISH, P1, 'bench')
        t.board.find_player_area(P1, 'bench').remove_child(odd)
        gloom_b = t.put(GLOOM, P1, 'bench')
        seen = {}

        def pick(cands, prompt):
            seen['c'] = list(cands)
            return cands[0]
        t.pokemon = pick
        penny = t.put(PENNY, P1, 'hand')
        if t.can(penny, 'UseTrainerCard'):
            await t.play(penny)
        self.assertNotIn(gloom_b, seen.get('c', []))
        self.assertNotIn(gloom_b, t.zone(P1, 'hand'))   # (Snorlax was the only Basic)

    # --- Aromatic Grass Energy (VIV 162) ------------------------------------
    async def test_aromatic_grass_cures_and_protects_grass_holder(self):
        t = self.table()
        odd = t.put(ODDISH, P1, 'active')
        self.big(odd)
        odd.set_attribute(AttrID.SPECIAL_CONDITIONS, [POISONED])
        await t.play(t.put(AROMATIC, P1, 'hand'), targets=[odd.entity_id])
        self.assertEqual(t.conditions(odd), set())
        t.next_turn()
        mis = self.new_opp_active(t, MISDREAVUS)
        t.energy(mis, P)
        await t.attack(mis, 'Confuse Ray', pid=P2)
        self.assertNotIn(CONFUSED, t.conditions(odd))

    async def test_aromatic_grass_does_not_protect_non_grass_holder(self):
        t = self.table()
        me = t.put(self.filler, P1, 'active')
        self.big(me)
        me.set_attribute(AttrID.SPECIAL_CONDITIONS, [POISONED])
        await t.play(t.put(AROMATIC, P1, 'hand'), targets=[me.entity_id])
        self.assertIn(POISONED, t.conditions(me))
        t.next_turn()
        mis = self.new_opp_active(t, MISDREAVUS)
        t.energy(mis, P)
        await t.attack(mis, 'Confuse Ray', pid=P2)
        self.assertIn(CONFUSED, t.conditions(me))

    # --- Glimwood Tangle (DAA 162) ------------------------------------------
    async def test_glimwood_reflip_after_tails(self):
        t = self.table(RealCoinTable)
        t.stadium(GLIMWOOD, P2)                  # any owner: "each player"
        ex = t.put(EXEGGUTOR, P1, 'active')
        t.energy(ex, G, 3)
        t.rng = [False, True]                    # tails, then the re-flip is heads
        t.yes = True
        await t.attack(ex, 'Stomp')
        self.assertEqual(400 - t.hp(self.opp), 90)
        self.assertTrue(t.state.attack_coin_reroll_used)

    async def test_glimwood_reflip_declined_keeps_result(self):
        t = self.table(RealCoinTable)
        t.stadium(GLIMWOOD, P1)
        ex = t.put(EXEGGUTOR, P1, 'active')
        t.energy(ex, G, 3)
        t.rng = [False, True]
        t.yes = False
        await t.attack(ex, 'Stomp')
        self.assertEqual(400 - t.hp(self.opp), 60)

    async def test_glimwood_also_for_opponent_next_turn(self):
        t = self.table(RealCoinTable)
        t.stadium(GLIMWOOD, P1)
        me = t.put(self.filler, P1, 'active')
        self.big(me)
        t.state.attack_coin_reroll_used = True   # P1 already used it this turn
        t.next_turn()
        self.assertFalse(t.state.attack_coin_reroll_used)
        ex = self.new_opp_active(t, EXEGGUTOR)
        t.energy(ex, G, 3)
        t.rng = [False, True]
        await t.attack(ex, 'Stomp', pid=P2)
        self.assertEqual(400 - t.hp(me), 90)

    async def test_no_reflip_without_glimwood(self):
        t = self.table(RealCoinTable)
        ex = t.put(EXEGGUTOR, P1, 'active')
        t.energy(ex, G, 3)
        t.rng = [False, True]
        await t.attack(ex, 'Stomp')
        self.assertEqual(400 - t.hp(self.opp), 60)
        self.assertFalse(any('flipping again' in (p or '') for p in t.prompts))

    # --- Trick Coin (PHF 108) -----------------------------------------------
    async def test_trick_coin_reflip_for_holder(self):
        t = self.table(RealCoinTable)
        ex = t.put(EXEGGUTOR, P1, 'active')
        t.energy(ex, G, 3)
        await t.play(t.put(TRICK_COIN, P1, 'hand'), targets=[ex.entity_id])
        t.rng = [False, True]
        await t.attack(ex, 'Stomp')
        self.assertEqual(400 - t.hp(self.opp), 90)

    async def test_trick_coin_on_other_pokemon_gives_no_reflip(self):
        t = self.table(RealCoinTable)
        ex = t.put(EXEGGUTOR, P1, 'active')
        t.energy(ex, G, 3)
        other = t.put(self.filler, P1, 'bench')
        t.attach(TRICK_COIN, other)
        t.rng = [False, True]
        await t.attack(ex, 'Stomp')
        self.assertEqual(400 - t.hp(self.opp), 60)

    async def test_trick_coin_does_not_help_opponent(self):
        t = self.table(RealCoinTable)
        me = t.put(self.filler, P1, 'active')
        self.big(me)
        t.attach(TRICK_COIN, me)
        t.next_turn()
        ex = self.new_opp_active(t, EXEGGUTOR)
        t.energy(ex, G, 3)
        t.rng = [False, True]
        await t.attack(ex, 'Stomp', pid=P2)
        self.assertEqual(400 - t.hp(me), 60)


if __name__ == '__main__':
    unittest.main()
