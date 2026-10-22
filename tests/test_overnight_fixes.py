"""Player reports and overnight sweep:
* Kyogre (ME1) Riptide did only 20: singular "Energy card in your discard
  pile" wasn't counted (also Trashalanche, Trash Slash, Venting Anger...).
* TM: Evolution (and the other "for each of those Pokemon, search your deck
  for a card that evolves from that Pokemon") never evolved anything.
* Antique fossils: discard-from-play action, and the evolves-from id the
  client matches against the fossil's real (Trainer) name key."""
import json
import unittest

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from spirit.game.attributes import AttrID, PokemonTypes
from spirit.game.data_utils import CARD_DEFS_BY_GUID, def_for
from spirit.game.session.effects import EffectContext
from spirit.tools.effect_smoke import P1, P2


class OvernightFixTests(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    def clear(self, rig, pid, zone):
        area = rig.board.find_player_area(pid, zone)
        lost = rig.board.find_player_area(pid, 'lostZone')
        for card in list(area.children):
            rig.board.move_card(card.entity_id, lost.entity_id)
        return area

    async def attack(self, rig, attacker, path, title):
        attack = next(a for a in fixtures.definition(path).abilities if a.title == title)
        defender = rig.board.active_pokemon(P2)
        defender.set_attribute(AttrID.HP, 5000)
        ctx = EffectContext(rig.session, P1, attacker, attack)
        await attack.effect(ctx)
        for action in list(ctx.deferred_actions):
            await action()
        return 5000 - defender.get_attribute(AttrID.HP)

    async def test_riptide_counts_then_shuffles(self):
        rig, e = self.rig('ME1.Kyogre_34')
        discard = self.clear(rig, P1, 'discard')
        water = next(d for d in CARD_DEFS_BY_GUID.values()
                     if d.display_name == 'Basic Water Energy' or d.display_name == 'Water Energy')
        for _ in range(7):
            self.add(rig, water, P1, 'discard')
        self.assertEqual(await self.attack(rig, e['target'], 'ME1.Kyogre_34', 'Riptide'), 140)
        self.assertEqual(len(discard.children), 0)

    async def test_trashalanche_counts_opponent_items(self):
        rig, e = self.rig('SM2.Garbodor_51')
        self.clear(rig, P2, 'discard')
        for path in ('ME1.RareCandy_125', 'BW9.FloatStone_99', 'SV065.NightStretcher_61'):
            self.add(rig, fixtures.definition(path), P2, 'discard')
        # Current rules: a Pokemon Tool is no longer an Item card.
        self.assertEqual(await self.attack(rig, e['target'], 'SM2.Garbodor_51', 'Trashalanche'), 40)

    async def test_tm_evolution_evolves_benched_pokemon_and_fossils(self):
        rig, e = self.rig('BW7.Charmander_18')
        bench = self.clear(rig, P1, 'bench')
        charmander = self.add(rig, fixtures.definition('BW7.Charmander_18'), P1, 'bench')
        fossil = self.add(rig, fixtures.definition('ME5.AntiqueSkullFossil_73'), P1, 'bench')
        charmeleon = self.add(rig, fixtures.definition('BW7.Charmeleon_19'), P1, 'deck')
        cranidos = self.add(rig, fixtures.definition('ME5.Cranidos_44'), P1, 'deck')
        tm = fixtures.definition('SV4.TechnicalMachineEvolution_178')
        attack = next(a for a in list(tm.abilities) + list(tm.granted_abilities or [])
                      if a.title == 'Evolution')
        ctx = EffectContext(rig.session, P1, e['target'], attack)
        await attack.effect(ctx)
        self.assertIs(charmander.parent, charmeleon)
        self.assertIs(fossil.parent, cranidos)

    async def test_singular_wording_formulas(self):
        # "for each damage counter on this Pokemon" / "for each card in your hand"
        from spirit.game.session import passives
        rig, e = self.rig('SM7.Donphan_73')
        me = e['target']
        me.set_attribute(AttrID.HP, passives.effective_max_hp(rig.board, me) - 40)
        rig.board.active_pokemon(P2).set_attribute(AttrID.HP, 5000)
        defender = rig.board.active_pokemon(P2)
        attack = next(a for a in fixtures.definition('SM7.Donphan_73').abilities if a.title == 'Flail')
        ctx = EffectContext(rig.session, P1, me, attack)
        await attack.effect(ctx)
        self.assertIn(5000 - defender.get_attribute(AttrID.HP), (40, 80))  # x2 if weak
        rig, e = self.rig('SV4.Ambipom_146')
        hand = len(rig.board.find_player_area(P1, 'hand').children)
        self.assertGreater(hand, 1)
        self.assertEqual(await self.attack(rig, e['target'], 'SV4.Ambipom_146', 'Hand Fling'), 20 * hand)

    async def test_fallback_formulas(self):
        # Previously fell back to printed damage.
        rig, e = self.rig('XY7.Metagross_50')
        hand = len(rig.board.find_player_area(P1, 'hand').children)
        self.assertEqual(await self.attack(rig, e['target'], 'XY7.Metagross_50',
                                           'Machine Gun Stomp'), 20 + 10 * hand)
        rig, e = self.rig('SM10.Hypno_72')
        opp_hand = len(rig.board.find_player_area(P2, 'hand').children)
        self.assertEqual(await self.attack(rig, e['target'], 'SM10.Hypno_72',
                                           'Stir the Brain'), 30 + 10 * opp_hand)

    async def test_venom_fever_needs_poison(self):
        from spirit.game.attributes import SpecialConditions
        rig, e = self.rig('SM8.Toxapex_69')
        self.assertEqual(await self.attack(rig, e['target'], 'SM8.Toxapex_69', 'Venom Fever'), 0)
        rig, e = self.rig('SM8.Toxapex_69')
        defender = rig.board.active_pokemon(P2)
        await EffectContext(rig.session, P2, defender, None).apply_special_condition(
            defender, SpecialConditions.POISONED)
        from spirit.game.session import passives
        defender.set_attribute(AttrID.HP, passives.effective_max_hp(rig.board, defender) - 40)
        attack = next(a for a in fixtures.definition('SM8.Toxapex_69').abilities
                      if a.title == 'Venom Fever')
        ctx = EffectContext(rig.session, P1, e['target'], attack)
        dealt = []
        original = ctx.deal_damage
        async def record(amount=None, *args, **kwargs):
            dealt.append(amount)
            return await original(amount, *args, **kwargs)
        ctx.deal_damage = record
        await attack.effect(ctx)
        self.assertEqual(dealt[0], 200)          # 4 counters x 50

    async def test_tm_evolution_turn_one_going_second_on_new_bench(self):
        rig, e = self.rig('BW7.Charmander_18')
        self.clear(rig, P1, 'bench')
        ts = rig.session.turn_state
        ts.turn_number = 2                                   # first turn, going second
        fossil = self.add(rig, fixtures.definition('ME5.AntiqueSkullFossil_73'), P1, 'bench')
        charmander = self.add(rig, fixtures.definition('BW7.Charmander_18'), P1, 'bench')
        for card in (fossil, charmander):
            ts.entered_play_turn[card.entity_id] = 2         # benched this turn
        cranidos = self.add(rig, fixtures.definition('ME5.Cranidos_44'), P1, 'deck')
        charmeleon = self.add(rig, fixtures.definition('BW7.Charmeleon_19'), P1, 'deck')
        tm = fixtures.definition('SV4.TechnicalMachineEvolution_178')
        attack = next(a for a in list(tm.abilities) + list(tm.granted_abilities or [])
                      if a.title == 'Evolution')
        ctx = EffectContext(rig.session, P1, e['target'], attack)
        await attack.effect(ctx)
        self.assertIs(fossil.parent, cranidos)
        self.assertIs(charmander.parent, charmeleon)

    def test_antique_fossils_can_be_discarded_and_match_their_evolutions(self):
        skull = fixtures.definition('ME5.AntiqueSkullFossil_73')
        self.assertIn('Discard', [a.title for a in skull.abilities])
        cranidos = fixtures.definition('ME5.Cranidos_44')
        evolves = json.loads(cranidos.extra_attributes[str(AttrID.EVOLVES_FROM.value)]['value'])
        self.assertEqual(evolves['id'], skull.name)


if __name__ == "__main__":
    unittest.main()
