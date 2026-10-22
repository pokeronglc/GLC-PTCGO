"""Attacks that give a Special Condition only when something is true
("If your opponent's Active Pokémon is a Metal Pokémon, it is now
Paralyzed").  Each card is checked with the condition met and not met.
"""
import unittest

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table
from tests.sweep_core import neutral, pay_cost
from spirit.game.attributes import AttrID, PokemonTypes as T
from spirit.tools.effect_smoke import P1, P2


def types(*kinds):
    def setup(t, me, opp):
        opp.set_attribute(AttrID.POKEMON_TYPES, [k.value for k in kinds])
    return setup


def my_energy(kind):
    def setup(t, me, opp):
        t.energy(me, kind)
    return setup


def opp_energy(kind):
    def setup(t, me, opp):
        t.energy(opp, kind)
    return setup


def stadium(owner):
    def setup(t, me, opp):
        from spirit.game.data_utils import CARD_DEFS_BY_GUID, StadiumCardDef
        spec = next(d for d in CARD_DEFS_BY_GUID.values() if isinstance(d, StadiumCardDef)
                    and d.display_name == 'Training Court') if False else 'SWSH2.TrainingCourt_169'
        t.stadium(spec, owner)
    return setup


def hand(pid, n):
    def setup(t, me, opp):
        area = t.zone(pid, 'hand')
        for card in list(area):
            t.board.find_player_area(pid, 'hand').remove_child(card)
        for _ in range(n):
            t.put(t.test.item, pid, 'hand')
    return setup


def prizes(pid, n):
    def setup(t, me, opp):
        t.set_prizes(pid, n)
    return setup


def evolved_from(spec):
    def setup(t, me, opp):
        under = t.put(spec, P1, 'hand')
        t.board.attach_card(under.entity_id, me.entity_id)
        t.state.entered_play_turn[me.entity_id] = t.state.turn_number
    return setup


def damaged(t, me, opp):
    from spirit.game.session.passives import effective_max_hp
    me.set_attribute(AttrID.HP, effective_max_hp(t.board, me) - 30)


def tool(t, me, opp):
    from spirit.game.data_utils import CARD_DEFS_BY_GUID, PokemonToolCardDef
    t.attach('SWSH1.AirBalloon_156', me)


def opp_tool(t, me, opp):
    t.attach('SWSH1.AirBalloon_156', opp)


def opp_confused(t, me, opp):
    from spirit.game.attributes import SpecialConditions
    opp.set_attribute(AttrID.SPECIAL_CONDITIONS, ['Confused'])


def opp_energy_in_hand(t, me, opp):
    t.put(t.basic_energy(T.WATER), P2, 'hand')


# (card, attack, setup making it true, opponent conditions, attacker conditions)
CASES = [
    ('BW2.Simisage_2', "Fire's Power", my_energy(T.FIRE), {'Burned'}, set()),
    ('BW2.Simisear_19', "Water's Power", my_energy(T.WATER), {'Asleep'}, set()),
    ('BW4.Simisear_16', 'Stadium Burn', stadium(P2), {'Burned'}, set()),
    ('BW4.Simipour_29', 'Stadium Wave', stadium(P2), {'Asleep'}, set()),
    ('Promo_SM.Xurkitree_116', 'Cablegram', prizes(P1, 3), {'Paralyzed'}, set()),
    ('SM11.Abomasnow_42', 'Quick Freeze', opp_energy(T.WATER), {'Paralyzed'}, set()),
    ('SM12.Kricketune_14', 'Improvisational Performance', hand(P1, 3), {'Confused'}, set()),
    ('SM4.Beedrill_3', 'Sudden Sting', evolved_from('SM4.Kakuna_2'), {'Paralyzed', 'Poisoned'}, set()),
    ('SM5.Electivire_44', 'Steel Short', types(T.METAL), {'Paralyzed'}, set()),
    ('SM6.Barbaracle_67', 'Seven Shock', hand(P1, 7), {'Paralyzed'}, set()),
    ('SM6.Pangoro_78', 'Untamed Punch', damaged, {'Confused'}, {'Confused'}),
    ('SV07.Togedemaru_54', 'Electrifying Chance', prizes(P1, 1), {'Paralyzed'}, set()),
    ('SWSH1.Lanturn_69', 'Strobe Shock', opp_energy_in_hand, {'Paralyzed'}, set()),
    ('SWSH10.HisuianArcanine_71', 'Scorching Horn', my_energy(T.FIRE), {'Burned'}, set()),
    ('SWSH11.Magearna_128', 'Windup Beam', tool, {'Confused'}, set()),
    ('SWSH8.Eelektross_97', 'Upper Shock', evolved_from('SWSH8.Eelektrik_96'), {'Paralyzed'}, set()),
    ('SWSH8.Durant_184', 'Adversity Jaws', types(T.FIRE), {'Paralyzed'}, set()),
    ('SWSH9.Dedenne_67', 'Dede-Flash', prizes(P2, 1), {'Confused'}, set()),
    ('XY11.Amoonguss_13', 'Strange Reaction', opp_confused, {'Paralyzed'}, set()),
    ('XY8.Abomasnow_40', 'Ice Age', types(T.DRAGON), {'Paralyzed'}, set()),
    ('XY9.Cloyster_24', 'Sudden Grip', evolved_from('XY9.Shellder_23'), {'Paralyzed'}, set()),
    ('SM8.Pachirisu_80', 'Overshort', opp_tool, {'Paralyzed'}, set()),
    ('SV09.NsJoltik_49', 'Zapping Short', opp_tool, {'Paralyzed'}, set()),
    ('SM6.Bergmite_29', 'Break Open', stadium(P2), {'Paralyzed'}, set()),
]


class ConditionalStatusAttacks(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    async def run_case(self, spec, title, setup):
        t = Table(self)
        me = neutral(t.put(spec, P1, 'active'))
        neutral(t.put(self.filler, P1, 'bench'))
        opp = neutral(t.put(self.filler, P2, 'active'))
        neutral(t.put(self.filler, P2, 'bench'))
        opp.set_attribute(AttrID.POKEMON_TYPES, [T.COLORLESS.value])
        pay_cost(t, me, next(a for a in fixtures.definition(spec).abilities if a.title == title))
        if setup is not None:
            setup(t, me, opp)
        entry = t.attack_offer(me, title)
        self.assertIsNotNone(entry, f"{spec} {title} not offered")
        await t.do(entry)
        before = {'Confused'} if setup is opp_confused else set()
        return set(t.conditions(t.active(P2))) - before, set(t.conditions(me))

    async def test_conditions(self):
        for spec, title, setup, want_opp, want_self in CASES:
            with self.subTest(card=spec, met=True):
                self.assertEqual(await self.run_case(spec, title, setup), (want_opp, want_self))
            if setup is opp_confused:
                continue
            with self.subTest(card=spec, met=False):
                self.assertEqual(await self.run_case(spec, title, None), (set(), set()))


if __name__ == "__main__":
    unittest.main()
