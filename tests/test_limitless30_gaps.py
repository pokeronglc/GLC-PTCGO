"""Limitless 30-deck list (Oct 13): the last cards whose text no test ran.

Ariados SWSH11 113 String Bind (Retreat Lock), Morpeko SV06 72 Pick and
Stick + Rotom SV1 70 Junk Hunt (Shock Lock), Rescue Scarf BW6 115
(TerraPlume), Lokix SV2 21 Assaulting Kick (Grassy Owl), Solrock SM3 69
Solar Heat (Drill Mill).
"""
import unittest

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table
from spirit.game.attributes import AttrID, PokemonTypes
from spirit.game.session.effects import EffectContext
from spirit.tools.effect_smoke import P1, P2

G, L, D, F = (PokemonTypes.GRASS, PokemonTypes.LIGHTNING,
              PokemonTypes.DARKNESS, PokemonTypes.FIGHTING)


def neutral(p, hp=None):
    p.set_attribute(AttrID.WEAKNESS_TYPES, [])
    p.set_attribute(AttrID.RESISTANCE_TYPES, [])
    if hp is not None:
        p.set_attribute(AttrID.HP, hp)
    return p


class Limitless30Gaps(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    def table(self, spec, kind, count=3):
        t = Table(self)
        me = t.put(spec, P1, 'active')
        t.energy(me, kind, count)
        opp = neutral(t.put(self.filler, P2, 'active'), hp=400)
        neutral(t.put(self.filler, P2, 'bench'))
        return t, me, opp

    # --- Ariados: 10 + 30 per Colorless in the Defending Retreat Cost ------
    async def test_string_bind_counts_retreat_cost(self):
        for cost in (0, 1, 3):
            with self.subTest(cost=cost):
                t, me, opp = self.table('SWSH11.Ariados_113', D)
                opp.set_attribute(AttrID.RETREAT_COST, cost)
                await t.attack(me, 'String Bind')
                self.assertEqual(400 - t.hp(opp), 10 + 30 * cost)

    async def test_string_bind_uses_current_retreat_cost(self):
        """Float Stone: 'has no Retreat Cost' -> nothing to count."""
        t, me, opp = self.table('SWSH11.Ariados_113', D)
        opp.set_attribute(AttrID.RETREAT_COST, 3)
        t.attach('XY8.FloatStone_137', opp)
        self.assertEqual(t.retreat(opp), 0)
        await t.attack(me, 'String Bind')
        self.assertEqual(400 - t.hp(opp), 10)


    async def test_same_wording_attacks_use_current_retreat_cost(self):
        """Every 'for each Colorless in your opponent's Active Pokemon's
        Retreat Cost' attack counts the cost as it is now (Float Stone -> 0)."""
        cases = [('SWSH2.Probopass_131', None),
                 ('SWSH11.Bronzong_126', None), ('SWSH6.Tsareena_15', None),
                 ('SWSH9.Flygon_76', None), ('SWSH1.Drednaw_61', None),
                 ('SWSH4.Mudsdale_97', None)]
        for spec, title in cases:
            d = fixtures.definition(spec)
            title = title or next(a.title for a in d.abilities
                                  if 'Retreat Cost' in (getattr(a, 'game_text', '') or '')
                                  and 'for each' in a.game_text)
            dmg = {}
            for stone in (False, True):
                t, me, opp = self.table(spec, PokemonTypes.COLORLESS, 0)
                opp.set_attribute(AttrID.RETREAT_COST, 3)
                if stone:
                    t.attach('XY8.FloatStone_137', opp)
                ctx = await t.effect(spec, me, title)
                dmg[stone] = 400 - t.hp(opp)
            with self.subTest(spec):
                self.assertNotEqual(dmg[False], dmg[True])

    # --- Morpeko: up to 2 basic Energy from discard, any way you like ------
    async def test_pick_and_stick_attaches_two_from_discard(self):
        t, me, opp = self.table('SV06.Morpeko_72', L, 1)
        mate = t.put(self.filler, P1, 'bench')
        e1 = t.put(t.basic_energy(G), P1, 'discard')
        e2 = t.put(t.basic_energy(F), P1, 'discard')
        t.put(self.item, P1, 'discard')
        t.pokemon = lambda cands, prompt: mate if mate in cands else cands[0]
        await t.attack(me, 'Pick and Stick')
        self.assertEqual(sorted(c.entity_id for c in mate.children if c in (e1, e2)),
                         sorted([e1.entity_id, e2.entity_id]))
        self.assertNotIn(e1, t.zone(P1, 'discard'))
        self.assertEqual(400 - t.hp(opp), 0)

    async def test_pick_and_stick_up_to_means_zero_is_fine(self):
        t, me, opp = self.table('SV06.Morpeko_72', L, 1)
        await t.attack(me, 'Pick and Stick')              # empty discard: no crash
        self.assertEqual(len(t.zone(P1, 'discard')), 0)

    # --- Rotom: an Item from discard to hand ------------------------------
    async def test_junk_hunt_returns_an_item_only(self):
        t, me, opp = self.table('SV1.Rotom_70', L, 1)
        item = t.put(self.item, P1, 'discard')
        energy = t.put(t.basic_energy(G), P1, 'discard')
        await t.attack(me, 'Junk Hunt')
        self.assertIn(item, t.zone(P1, 'hand'))
        self.assertIn(energy, t.zone(P1, 'discard'))

    # --- Lokix: +100 if it evolved from Nymble this turn -------------------
    async def lokix(self, evolve_now):
        t = Table(self)
        nymble = t.put('SV2.Nymble_19', P1, 'active')
        t.energy(nymble, G, 2)
        opp = neutral(t.put(self.filler, P2, 'active'), hp=400)
        neutral(t.put(self.filler, P2, 'bench'))
        if evolve_now:
            card = t.put('SV2.Lokix_21', P1, 'hand')
            await t.play(card, targets=[nymble.entity_id])
            lokix = t.active(P1)
        else:
            lokix = t.put('SV2.Lokix_21', P1, 'active')
            t.energy(lokix, G, 2)
            t.board.find_player_area(P1, 'activePokemonArea').remove_child(nymble)
        await t.attack(lokix, 'Assaulting Kick')
        return 400 - t.hp(opp)

    async def test_assaulting_kick_bonus_when_evolved_this_turn(self):
        self.assertEqual(await self.lokix(True), 130)

    async def test_assaulting_kick_no_bonus_otherwise(self):
        self.assertEqual(await self.lokix(False), 30)

    # --- Solrock: +20 with any Stadium in play -----------------------------
    async def test_solar_heat(self):
        for stadium in (None, P1, P2):
            with self.subTest(stadium=stadium):
                t, me, opp = self.table('SM3.Solrock_69', F, 1)
                if stadium:
                    t.stadium('SV2.Artazon_171', stadium)
                await t.attack(me, 'Solar Heat')
                self.assertEqual(400 - t.hp(opp), 40 if stadium else 20)

    # --- Rescue Scarf: KO'd Pokemon goes to hand, attachments discarded -----
    async def scarf(self, by_attack):
        t = Table(self)
        mon = neutral(t.put(self.filler, P1, 'active'))
        t.put(self.filler, P1, 'bench')
        opp = t.put('SWSH11.Ariados_113', P2, 'active')
        t.energy(opp, D, 1)
        neutral(t.put(self.filler, P2, 'bench'))
        energy = t.energy(mon, G)
        scarf = t.put('BW6.RescueScarf_115', P1, 'hand')
        await t.play(scarf, targets=[mon.entity_id])
        self.assertIn(scarf, list(mon.children))
        mon.set_attribute(AttrID.HP, 10)
        if by_attack:
            t.next_turn()
            await t.attack(opp, 'String Bind', pid=P2)
        else:                       # e.g. Poison at Pokemon Checkup
            ctx = EffectContext(t.session, P2, opp, None)
            mon.set_attribute(AttrID.HP, 0)
            ctx.knockouts.append(mon)
            await t.knockouts(ctx)
        return t, mon, scarf, energy

    async def test_rescue_scarf_returns_pokemon_knocked_out_by_attack(self):
        t, mon, scarf, energy = await self.scarf(True)
        self.assertIn(mon, t.zone(P1, 'hand'))
        self.assertIn(scarf, t.zone(P1, 'discard'))
        self.assertIn(energy, t.zone(P1, 'discard'))

    async def test_rescue_scarf_not_for_other_knockouts(self):
        t, mon, scarf, energy = await self.scarf(False)
        self.assertIn(mon, t.zone(P1, 'discard'))


if __name__ == '__main__':
    unittest.main()
