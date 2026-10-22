"""Bug hunt round 7, chunk 28: Minun, Heat Fire Energy, Allister, Mesagoza,
Primordial Altar, Fezandipiti, Litwick, Maintenance, Amaura, Lapras, Geeta,
Lt. Surge's Bargain, Squirtle, Wartortle, Blastoise -- each checked against
its printed text, including the cases where it should NOT work."""
import unittest
from unittest.mock import patch

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table, ASLEEP
from spirit.game.attributes import AttrID, PokemonTypes
from spirit.game.data_utils import Attack, def_for
from spirit.game.session.effects import EffectContext
from spirit.game.session.passives import effective_max_hp
from spirit.tools.effect_smoke import P1, P2

FIRE, WATER, DARK = PokemonTypes.FIRE, PokemonTypes.WATER, PokemonTypes.DARKNESS
PSY, LIGHT = PokemonTypes.PSYCHIC, PokemonTypes.LIGHTNING

MINUN, PLUSLE = 'SV4.Minun_61', 'SV4.Plusle_60'
HEAT_FIRE = 'SWSH3.HeatFireEnergy_174'
ALLISTER = 'SWSH4.Allister_146'
MESAGOZA = 'SV1.Mesagoza_178'
ALTAR = 'SWSH12.PrimordialAltar_161'
FEZ = 'SV06.Fezandipiti_96'
LITWICK = 'SM11.Litwick_28'
MAINT = 'XY12.Maintenance_79'
AMAURA = 'ME3.Amaura_23'
LAPRAS = 'SV035.Lapras_131'
GEETA = 'SV3.Geeta_188'
BARGAIN = 'ME1.LtSurgesBargain_120'
SQUIRTLE, WARTORTLE, BLASTOISE = 'SV035.Squirtle_7', 'SV035.Wartortle_8', 'PGO.Blastoise_17'


def name(card):
    return def_for(card.archetype_id).display_name


class RecTable(Table):
    """Table that also records who is asked yes/no questions."""

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.asked = []      # (player_id, prompt)
        self.choice_idx = 0  # answer for present_card_choice / choose menus

    def _patches(self):
        table = self
        out = [p for p in super()._patches() if p.attribute != 'ask_yes_no']

        async def ask_yes_no(ctx, prompt, player_id=None):
            table.asked.append((player_id or ctx.player_id, prompt))
            table.prompts.append(prompt)
            return table.yes(prompt) if callable(table.yes) else table.yes

        async def present_card_choice(ctx, card, prompt, buttons, player_id=None):
            table.asked.append((player_id or ctx.player_id, prompt))
            return table.choice_idx

        async def choose(ctx, prompt, buttons, *a, **k):
            table.asked.append((k.get('player_id') or ctx.player_id, prompt))
            return table.choice_idx

        out += [patch.object(EffectContext, 'ask_yes_no', ask_yes_no),
                patch.object(EffectContext, 'present_card_choice', present_card_choice),
                patch.object(EffectContext, 'choose', choose)]
        return out


class Chunk28(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    def table(self):
        t = RecTable(self)
        self.opp = t.put(self.filler, P2, 'active')
        self.neutral(self.opp)
        return t

    @staticmethod
    def neutral(p, hp=400):
        p.set_attribute(AttrID.WEAKNESS_TYPES, [])
        p.set_attribute(AttrID.RESISTANCE_TYPES, [])
        if hp is not None:
            p.set_attribute(AttrID.HP, hp)

    def mine(self, t, spec, kind=None, count=0, zone='active', hp=None):
        p = t.put(spec, P1, zone)
        self.neutral(p, hp)
        if count:
            t.energy(p, kind, count)
        return p

    def clear(self, t, pid, zone):
        area = t.board.find_player_area(pid, {'hand': 'hand', 'deck': 'deck'}[zone])
        for c in list(area.children):
            area.remove_child(c)

    def is_energy(self, card):
        return card.archetype_id.lower() in {g.lower() for g in self.energies.values()}

    def is_kind(self, card, kind):
        return card.archetype_id.lower() == self.energies[kind.value].lower()

    def energies_on(self, p):
        return [c for c in p.children if self.is_energy(c)]

    def dealt(self):
        return 400 - self.opp.get_attribute(AttrID.HP)

    def filler_attack(self):
        for a in def_for(self.opp.archetype_id).abilities:
            if isinstance(a, Attack) and a.damage:
                return a.title
        raise AssertionError('filler has no damaging attack')

    async def opp_attacks(self, t):
        # a Benched Pokémon so a Knock Out doesn't end the game
        self.mine(t, self.filler, zone='bench')
        t.energy(self.opp, WATER, 4)
        t.next_turn()
        await t.attack(self.opp, self.filler_attack(), pid=P2)

    # --- Minun PAR 61: Buddy Pulse ------------------------------------------
    async def test_minun_buddy_pulse_with_plusle(self):
        t = self.table()
        self.mine(t, MINUN)
        self.mine(t, PLUSLE, zone='bench')
        t.next_turn()
        e = t.put(t.basic_energy(WATER), P2, 'hand')
        await t.play(e, pid=P2, targets=[self.opp.entity_id])
        self.assertIn(e, self.opp.children)
        self.assertEqual(self.dealt(), 20)

    # BUG: Buddy Pulse ignores 'If you have Plusle in play' (bw_era energy-attach observer has no gate)
    async def test_minun_buddy_pulse_needs_plusle(self):
        t = self.table()
        self.mine(t, MINUN)
        self.mine(t, self.filler, zone='bench')
        t.next_turn()
        e = t.put(t.basic_energy(WATER), P2, 'hand')
        await t.play(e, pid=P2, targets=[self.opp.entity_id])
        self.assertIn(e, self.opp.children)
        self.assertEqual(self.dealt(), 0)

    # BUG: two Minun put 4 counters; 'doesn't stack' is ignored by the energy-attach observer
    async def test_minun_buddy_pulse_does_not_stack(self):
        t = self.table()
        self.mine(t, MINUN)
        self.mine(t, MINUN, zone='bench')
        self.mine(t, PLUSLE, zone='bench')
        t.next_turn()
        e = t.put(t.basic_energy(WATER), P2, 'hand')
        await t.play(e, pid=P2, targets=[self.opp.entity_id])
        self.assertEqual(self.dealt(), 20)

    async def test_minun_buddy_pulse_ignores_own_attachments(self):
        t = self.table()
        m = self.mine(t, MINUN, hp=None)
        self.mine(t, PLUSLE, zone='bench')
        e = t.put(t.basic_energy(LIGHT), P1, 'hand')
        await t.play(e, targets=[m.entity_id])
        self.assertIn(e, m.children)
        self.assertEqual(t.damage(m), 0)

    # --- Heat Fire Energy DAA 174 -------------------------------------------
    async def test_heat_fire_energy_plus20_on_fire_pokemon(self):
        t = self.table()
        lit = self.mine(t, LITWICK, hp=None)
        e = t.put(HEAT_FIRE, P1, 'hand')
        await t.play(e, targets=[lit.entity_id])
        self.assertIn(e, lit.children)
        self.assertEqual(effective_max_hp(t.board, lit), 80)
        # provides Fire: Find a Friend ([R]) is now usable
        self.assertIsNotNone(t.attack_offer(lit, 'Find a Friend'))

    async def test_heat_fire_energy_no_bonus_on_non_fire(self):
        t = self.table()
        snor = self.mine(t, self.filler, hp=None)
        before = effective_max_hp(t.board, snor)
        e = t.put(HEAT_FIRE, P1, 'hand')
        await t.play(e, targets=[snor.entity_id])
        self.assertIn(e, snor.children)
        self.assertEqual(effective_max_hp(t.board, snor), before)

    # --- Allister VIV 146 ----------------------------------------------------
    async def test_allister_draws_3_then_discards_up_to_3(self):
        t = self.table()
        self.mine(t, self.filler)
        self.clear(t, P1, 'hand')
        card = t.put(ALLISTER, P1, 'hand')
        keep = t.put(self.filler, P1, 'hand')
        deck_before = len(t.zone(P1, 'deck'))
        seen = []

        def picks(cards, count, prompt, display):
            seen.append(count)
            return [c for c in cards if c is not keep][:count]
        t.picks = picks
        await t.play(card)
        self.assertEqual(len(t.zone(P1, 'deck')), deck_before - 3)
        self.assertEqual(seen, [3])
        self.assertEqual(t.zone(P1, 'hand'), [keep])
        self.assertEqual(len(t.zone(P1, 'discard')), 4)   # Allister + 3

    async def test_allister_may_discard_just_one(self):
        t = self.table()
        self.mine(t, self.filler)
        self.clear(t, P1, 'hand')
        card = t.put(ALLISTER, P1, 'hand')
        t.picks = lambda cards, count, prompt, display: list(cards)[:1]
        await t.play(card)
        self.assertEqual(len(t.zone(P1, 'hand')), 2)
        self.assertEqual(len(t.zone(P1, 'discard')), 2)

    # --- Mesagoza SVI 178 ----------------------------------------------------
    def stadium_entry(self, t, stadium, pid=P1):
        return next(iter(t.offers(stadium, None, pid)), None)

    async def test_mesagoza_heads_finds_pokemon_once_per_turn(self):
        t = self.table()
        self.mine(t, self.filler)
        t.deck(P1, [LITWICK])
        st = t.stadium(MESAGOZA, P2)
        t.heads = True
        await t.do(self.stadium_entry(t, st))
        self.assertIn('Litwick', t.names(t.zone(P1, 'hand')))
        self.assertIsNone(self.stadium_entry(t, st))
        # the opponent may use it during their own turn
        t.deck(P2, [LITWICK])
        t.next_turn()
        entry = self.stadium_entry(t, st, P2)
        self.assertIsNotNone(entry)
        await t.do(entry, pid=P2)
        self.assertIn('Litwick', t.names(t.zone(P2, 'hand')))

    async def test_mesagoza_tails_finds_nothing(self):
        t = self.table()
        self.mine(t, self.filler)
        t.deck(P1, [LITWICK])
        st = t.stadium(MESAGOZA, P1)
        t.heads = False
        hand_before = len(t.zone(P1, 'hand'))
        await t.do(self.stadium_entry(t, st))
        self.assertEqual(len(t.zone(P1, 'hand')), hand_before)
        self.assertIn('Litwick', t.names(t.zone(P1, 'deck')))
        self.assertIsNone(self.stadium_entry(t, st))

    # --- Primordial Altar SIT 161 --------------------------------------------
    async def test_primordial_altar_may_discard_top_card(self):
        t = self.table()
        self.mine(t, self.filler)
        top = t.deck(P1, [LITWICK])[0]
        st = t.stadium(ALTAR, P2)
        t.choice_idx = 0
        await t.do(self.stadium_entry(t, st))
        self.assertIn(top, t.zone(P1, 'discard'))
        self.assertIsNone(self.stadium_entry(t, st))       # once per turn
        t.next_turn()
        self.assertIsNotNone(self.stadium_entry(t, st, P2))  # each player

    async def test_primordial_altar_may_keep_top_card(self):
        t = self.table()
        self.mine(t, self.filler)
        top = t.deck(P1, [LITWICK])[0]
        st = t.stadium(ALTAR, P1)
        t.choice_idx = 1
        await t.do(self.stadium_entry(t, st))
        self.assertIs(t.zone(P1, 'deck')[-1], top)
        self.assertNotIn(top, t.zone(P1, 'discard'))

    # --- Fezandipiti TWM 96 --------------------------------------------------
    async def test_fezandipiti_heads_prevents_with_darkness(self):
        t = self.table()
        fez = self.mine(t, FEZ, DARK, 1, hp=None)
        t.heads = True
        await self.opp_attacks(t)
        self.assertEqual(t.damage(fez), 0)

    async def test_fezandipiti_tails_or_no_darkness_takes_damage(self):
        t = self.table()
        fez = self.mine(t, FEZ, DARK, 1, hp=None)
        t.heads = False
        await self.opp_attacks(t)
        self.assertGreater(t.damage(fez), 0)
        t2 = self.table()
        fez2 = self.mine(t2, FEZ, PSY, 1, hp=None)
        t2.heads = True
        await self.opp_attacks(t2)
        self.assertGreater(t2.damage(fez2), 0)

    async def test_fezandipiti_energy_feather_30_per_energy(self):
        t = self.table()
        fez = self.mine(t, FEZ, PSY, 3)
        await t.attack(fez, 'Energy Feather')
        self.assertEqual(self.dealt(), 90)

    # --- Litwick UNM 28: Find a Friend ---------------------------------------
    async def test_litwick_find_a_friend_fire_only(self):
        t = self.table()
        lit = self.mine(t, LITWICK, FIRE, 1)
        t.deck(P1, [self.filler, LITWICK])
        offered = []
        t.picks = lambda cards, count, prompt, display: (offered.extend(cards), cards[:count])[1]
        await t.attack(lit, 'Find a Friend')
        self.assertEqual([name(c) for c in offered], ['Litwick'])
        self.assertEqual(t.names(t.zone(P1, 'hand')), ['Litwick'])

    # --- Maintenance EVO 79 --------------------------------------------------
    async def test_maintenance_shuffles_two_then_draws(self):
        t = self.table()
        self.mine(t, self.filler)
        self.clear(t, P1, 'hand')
        card = t.put(MAINT, P1, 'hand')
        a, b = t.put(LITWICK, P1, 'hand'), t.put(LITWICK, P1, 'hand')
        deck_before = len(t.zone(P1, 'deck'))
        await t.play(card)
        self.assertEqual(len(t.zone(P1, 'deck')), deck_before + 1)
        self.assertEqual(len(t.zone(P1, 'hand')), 1)
        self.assertIn(card, t.zone(P1, 'discard'))

    async def test_maintenance_needs_two_other_cards(self):
        t = self.table()
        self.mine(t, self.filler)
        self.clear(t, P1, 'hand')
        card = t.put(MAINT, P1, 'hand')
        t.put(LITWICK, P1, 'hand')
        self.assertFalse(t.can(card, 'UseTrainerCard'))
        t.put(LITWICK, P1, 'hand')
        self.assertTrue(t.can(card, 'UseTrainerCard'))

    # --- Amaura POR 23: Icy Wind ---------------------------------------------
    async def test_amaura_icy_wind_asleep(self):
        t = self.table()
        am = self.mine(t, AMAURA, WATER, 2)
        await t.attack(am, 'Icy Wind')
        self.assertEqual(self.dealt(), 50)
        self.assertIn(ASLEEP, t.conditions(self.opp))
        self.assertEqual(t.conditions(am), set())

    # --- Lapras MEW 131: Hop on My Back --------------------------------------
    async def test_lapras_hop_on_my_back_up_to_2_pokemon(self):
        t = self.table()
        lap = self.mine(t, LAPRAS, WATER, 1)
        t.deck(P1, [LITWICK, t.basic_energy(WATER), LITWICK, LITWICK])
        offered = []
        t.picks = lambda cards, count, prompt, display: (offered.append((len(cards), count)), cards[:count])[1]
        await t.attack(lap, 'Hop on My Back')
        self.assertEqual(offered, [(3, 2)])
        self.assertEqual(t.names(t.zone(P1, 'hand')), ['Litwick', 'Litwick'])

    # --- Geeta OBF 188 -------------------------------------------------------
    async def test_geeta_attaches_two_basic_energy_then_no_attack(self):
        t = self.table()
        act = self.mine(t, FEZ, PSY, 1)
        bench = self.mine(t, LITWICK, zone='bench')
        t.deck(P1, [t.basic_energy(FIRE), HEAT_FIRE, t.basic_energy(WATER), t.basic_energy(FIRE)])
        offered = []
        t.picks = lambda cards, count, prompt, display: (offered.extend(cards), cards[:count])[1]
        t.pokemon = lambda c, p: bench
        card = t.put(GEETA, P1, 'hand')
        self.assertIsNotNone(t.attack_offer(act, 'Energy Feather'))
        await t.play(card)
        self.assertEqual(len(self.energies_on(bench)), 2)
        self.assertNotIn('Heat Fire Energy', [name(c) for c in offered])
        self.assertIsNone(t.attack_offer(act, 'Energy Feather'))
        t.next_turn()
        t.next_turn()
        self.assertIsNotNone(t.attack_offer(act, 'Energy Feather'))

    # --- Lt. Surge's Bargain MEG 120 -----------------------------------------
    # BUG: opponent is never asked; generic 'draw 4 cards' fallback always runs, no prize branch
    async def test_lt_surges_bargain_yes_each_takes_a_prize(self):
        t = self.table()
        self.mine(t, self.filler)
        self.clear(t, P1, 'hand')
        self.clear(t, P2, 'hand')
        card = t.put(BARGAIN, P1, 'hand')
        t.yes = True
        await t.play(card)
        self.assertTrue(any(pid == P2 for pid, _ in t.asked), t.asked)
        self.assertEqual(len(t.zone(P1, 'prizes')), 5)
        self.assertEqual(len(t.zone(P2, 'prizes')), 5)
        self.assertEqual(len(t.zone(P1, 'hand')), 1)
        self.assertEqual(len(t.zone(P2, 'hand')), 1)

    async def test_lt_surges_bargain_no_draws_four(self):
        t = self.table()
        self.mine(t, self.filler)
        self.clear(t, P1, 'hand')
        card = t.put(BARGAIN, P1, 'hand')
        t.yes = False
        t.choice_idx = 1
        await t.play(card)
        self.assertEqual(len(t.zone(P1, 'prizes')), 6)
        self.assertEqual(len(t.zone(P2, 'prizes')), 6)
        self.assertEqual(len(t.zone(P1, 'hand')), 4)

    # --- Squirtle MEW 7: Withdraw --------------------------------------------
    async def test_squirtle_withdraw_heads_prevents_damage(self):
        t = self.table()
        sq = self.mine(t, SQUIRTLE, WATER, 1, hp=None)
        t.heads = True
        await t.attack(sq, 'Withdraw')
        await self.opp_attacks(t)
        self.assertIs(t.active(P1), sq)
        self.assertEqual(t.damage(sq), 0)

    async def test_squirtle_withdraw_tails_no_protection(self):
        t = self.table()
        sq = self.mine(t, SQUIRTLE, WATER, 1, hp=None)
        t.heads = False
        await t.attack(sq, 'Withdraw')
        await self.opp_attacks(t)
        knocked_out = sq in t.zone(P1, 'discard')
        self.assertTrue(knocked_out or t.damage(sq) > 0)

    # --- Wartortle MEW 8: Free Diving ----------------------------------------
    async def test_wartortle_free_diving_up_to_3_basic_water(self):
        t = self.table()
        war = self.mine(t, WARTORTLE, WATER, 1)
        self.clear(t, P1, 'hand')
        for _ in range(4):
            t.put(t.basic_energy(WATER), P1, 'discard')
        t.put(t.basic_energy(FIRE), P1, 'discard')
        t.put(HEAT_FIRE, P1, 'discard')
        offered = []
        t.picks = lambda cards, count, prompt, display: (offered.extend(cards), cards[:count])[1]
        await t.attack(war, 'Free Diving')
        hand = t.zone(P1, 'hand')
        self.assertEqual(len(hand), 3)
        self.assertTrue(all(self.is_kind(c, WATER) for c in hand))
        self.assertTrue(all(self.is_kind(c, WATER) for c in offered))

    # --- Blastoise PGO 17 ----------------------------------------------------
    async def test_blastoise_vitality_spring_attaches_and_ends_turn(self):
        t = self.table()
        bl = self.mine(t, BLASTOISE)
        bench = self.mine(t, SQUIRTLE, zone='bench')
        t.deck(P1, [t.basic_energy(WATER)] * 4 + [HEAT_FIRE] + [t.basic_energy(FIRE)] * 2)
        t.pokemon = lambda c, p: bench if 'Heat' in p or 'Fire' in p else bl
        t.yes = True
        ended = await t.use(bl, 'Vitality Spring')
        self.assertEqual(len(bl.children) + len(bench.children), 6)
        self.assertEqual(sum(1 for c in t.zone(P1, 'deck') if name(c) != 'Pokégear 3.0'), 1)
        self.assertTrue(ended, 'turn should end')

    async def test_blastoise_vitality_spring_no_reconfirm(self):
        # Oct 13 owner ruling: clicking the Ability is the "you may"; no
        # second yes/no, so the use always searches and ends the turn.
        t = self.table()
        bl = self.mine(t, BLASTOISE)
        t.deck(P1, [t.basic_energy(WATER)] * 2)
        asked = []
        t.yes = lambda prompt: asked.append(prompt) or False
        entry = t.ability_offer(bl, 'Vitality Spring')
        ended = await t.do(entry)
        self.assertEqual(asked, [])
        self.assertTrue(ended)

    async def test_blastoise_hydro_pump_counts_water_only(self):
        t = self.table()
        bl = self.mine(t, BLASTOISE, WATER, 2)
        t.energy(bl, FIRE, 2)
        await t.attack(bl, 'Hydro Pump')
        self.assertEqual(self.dealt(), 150)


if __name__ == '__main__':
    unittest.main()
