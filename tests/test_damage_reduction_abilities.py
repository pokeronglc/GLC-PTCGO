"""Every Pokémon Ability that reduces damage taken (42 wordings in the card
pool): applies when its conditions hold, and only then.

Board: P2 attacks with Dialga (Heavy Impact, 210, no text) into P1's Active.
No Weakness/Resistance anywhere; big HP so nothing is Knocked Out.
Each scenario states the expected reduction.
"""
import unittest

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table
from tests.sweep_core import pay_cost
from spirit.game.attributes import AttrID, PokemonTypes as T
from spirit.game.data_utils import Attack
from spirit.tools.effect_smoke import P1, P2

ATTACKER, ATTACK, BASE = 'SWSH7.Dialga_112', 'Heavy Impact', 210


class DamageReductionAbilities(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    def neutral(self, mon, hp=900, types=None):
        mon.set_attribute(AttrID.WEAKNESS_TYPES, [])
        mon.set_attribute(AttrID.RESISTANCE_TYPES, [])
        mon.set_attribute(AttrID.HP, hp)
        mon.attribute_originals[AttrID.HP.value] = hp     # max HP too ("full HP" checks)
        if types is not None:
            mon.set_attribute(AttrID.POKEMON_TYPES, [t.value for t in types])
        return mon

    async def taken(self, holder, *, holder_zone='active', target=None, target_types=None,
                    energy=(), attacker_types=None, damaged=False, extra_p1=(),
                    extra_p2=(), copies=1):
        """Damage P1's Active takes from Heavy Impact.  `target` None: the
        holder itself is the Active; otherwise that card is the Active and the
        holder sits on the Bench."""
        t = Table(self)
        # Dialga is a Dragon; default to Colorless so type-gated Abilities stay off.
        attacker = self.neutral(t.put(ATTACKER, P2, 'active'),
                                types=attacker_types or [T.COLORLESS])
        pay_cost(t, attacker, next(a for a in fixtures.definition(ATTACKER).abilities
                                   if isinstance(a, Attack) and a.title == ATTACK))
        if target is None:
            active = self.neutral(t.put(holder, P1, 'active'), types=target_types)
        else:
            active = self.neutral(t.put(target, P1, 'active'), types=target_types)
            self.neutral(t.put(holder, P1, 'bench'))
        for _ in range(copies - 1):
            self.neutral(t.put(holder, P1, 'bench'))
        for spec in extra_p1:
            self.neutral(t.put(spec, P1, 'bench'))
        for spec in extra_p2:
            self.neutral(t.put(spec, P2, 'bench'))
        for kind in energy:
            t.energy(active, kind)
        if damaged:
            active.set_attribute(AttrID.HP, 890)
        before = t.hp(active)
        t.next_turn()
        await t.attack(attacker, ATTACK, pid=P2)
        return before - t.hp(active)

    async def check(self, label, holder, reduction, **kw):
        with self.subTest(card=label, **{k: str(v) for k, v in kw.items()}):
            self.assertEqual(await self.taken(holder, **kw), BASE - reduction)

    # --- "This Pokémon takes N less damage" (no condition) ---------------------
    async def test_plain_self_reductions(self):
        for spec, n in (('SM9.Aegislash_109', 40), ('SWSH8.Cloyster_51', 30),
                        ('SV085.Furfrou_88', 20), ('SM11.Sewaddle_7', 10),
                        ('BW6.Bouffalant_110', 20), ('XY6.Shelgon_56', 10),
                        ('XY8.Snorlax_118', 30)):
            await self.check(spec, spec, n)
            await self.check(spec + ' (other Pokémon)', spec, 0, target=self.filler)

    # --- team-wide -----------------------------------------------------------
    async def test_team_wide(self):
        for spec, n in (('SV085.Bronzong_67', 10), ('XY5.Rhyperior_77', 10),
                        ('SWSH2.Aegislash_135', 30)):
            await self.check(spec, spec, n, target=self.filler)
        await self.check('Big Shield x2 (no stack)', 'SWSH2.Aegislash_135', 30,
                         target=self.filler, copies=2)

    async def test_active_only_team_wide(self):
        await self.check('Arcanine active', 'GUM.Arcanine_6', 30)
        await self.check('Arcanine benched', 'GUM.Arcanine_6', 0, target=self.filler)
        await self.check('Diancie active', 'SWSH4.Diancie_79', 30)
        await self.check('Lugia active', 'XY10.Lugia_78', 20)

    async def test_type_of_your_pokemon(self):
        await self.check('Dugtrio metal', 'SM10.AlolanDugtrio_122', 10,
                         target=self.filler, target_types=[T.METAL])
        await self.check('Dugtrio non-metal', 'SM10.AlolanDugtrio_122', 0, target=self.filler)
        await self.check('Leavanny grass', 'SM11.Leavanny_9', 40,
                         target=self.filler, target_types=[T.GRASS])
        await self.check('Leavanny non-grass', 'SM11.Leavanny_9', 0, target=self.filler)
        await self.check('Klinklang basic', 'SWSH9.Klinklang_104', 20, target=self.filler)

    # --- energy attached --------------------------------------------------------
    async def test_energy_attached_team_wide(self):
        # Was the reported bug: Tundra Wall reduced damage to every Pokémon.
        await self.check('Aurorus ME3 water energy', 'ME3.Aurorus_24', 50,
                         target=self.filler, energy=[T.WATER])
        await self.check('Aurorus ME3 no water energy', 'ME3.Aurorus_24', 0,
                         target=self.filler, energy=[T.FIRE])
        await self.check('Aurorus ME3 water type, no energy', 'ME3.Aurorus_24', 0,
                         target=self.filler, target_types=[T.WATER])
        await self.check('Aurorus ME3 x2 (no stack)', 'ME3.Aurorus_24', 50,
                         target=self.filler, energy=[T.WATER], copies=2)
        await self.check('Aurorus XY3 water type + water energy', 'XY3.Aurorus_26', 20,
                         target=self.filler, target_types=[T.WATER], energy=[T.WATER])
        await self.check('Aurorus XY3 water type, no energy', 'XY3.Aurorus_26', 0,
                         target=self.filler, target_types=[T.WATER])
        await self.check('Aurorus XY3 non-water + water energy', 'XY3.Aurorus_26', 0,
                         target=self.filler, energy=[T.WATER])
        await self.check('Klinklang BLK metal energy', 'ZSV10PT5.Klinklang_63', 20,
                         target=self.filler, energy=[T.METAL])
        await self.check('Klinklang BLK no metal energy', 'ZSV10PT5.Klinklang_63', 0,
                         target=self.filler, energy=[T.WATER])

    async def test_energy_attached_self(self):
        for spec, kind, n in (('SWSH3.Darkrai_105', T.DARKNESS, 20), ('SM9.Kakuna_4', T.GRASS, 30),
                              ('SM7.Lunala_70', T.PSYCHIC, 20), ('XY8.Raikou_55', T.LIGHTNING, 20),
                              ('DM.Shelgon_43', T.WATER, 20), ('SV09.Regirock_82', T.FIRE, 30)):
            await self.check(spec + ' with', spec, n, energy=[kind])
            await self.check(spec + ' without', spec, 0)
        await self.check('Darkrai wrong energy', 'SWSH3.Darkrai_105', 0, energy=[T.WATER])

    # --- attacker's type -----------------------------------------------------------
    async def test_attacker_type(self):
        for spec in ('SM3.Azumarill_35', 'ME2.Dewgong_22', 'XY3.Hariyama_52'):
            await self.check(spec + ' vs fire', spec, 30, attacker_types=[T.FIRE])
            await self.check(spec + ' vs water', spec, 30, attacker_types=[T.WATER])
            await self.check(spec + ' vs metal', spec, 0, attacker_types=[T.METAL])
        await self.check('Heliolisk vs water', 'Promo_XY.Heliolisk_47', 30, attacker_types=[T.WATER])
        await self.check('Heliolisk vs fire', 'Promo_XY.Heliolisk_47', 0, attacker_types=[T.FIRE])
        await self.check('Bewear vs metal', 'SM4.Bewear_56', 30, attacker_types=[T.METAL])
        await self.check('Bewear vs fire', 'SM4.Bewear_56', 0, attacker_types=[T.FIRE])
        await self.check('Clefable vs dragon', 'SWSH11.Clefable_63', 30,
                         target=self.filler, attacker_types=[T.DRAGON])
        await self.check('Clefable vs colorless', 'SWSH11.Clefable_63', 0, target=self.filler)

    async def test_rule_box_only_abilities_do_nothing_here(self):
        # GLC has no Pokémon V / TAG TEAM: these never apply.
        for spec in ('SWSH10.Bastiodon_110', 'SWSH9.Escavalier_101', 'SM11.Lucario_117'):
            await self.check(spec, spec, 0, target=self.filler)

    # --- other conditions ------------------------------------------------------
    async def test_full_hp(self):
        await self.check('Eiscue full HP', 'SWSH2.Eiscue_54', 60)
        await self.check('Eiscue damaged', 'SWSH2.Eiscue_54', 0, damaged=True)
        await self.check('Gigalith full HP', 'XY4.Gigalith_50', 50)
        await self.check('Gigalith damaged', 'XY4.Gigalith_50', 0, damaged=True)

    async def test_retreat_cost_scaling(self):
        t = Table(self)
        retreat = t.retreat(t.put(ATTACKER, P2, 'active'))
        await self.check('Klinklang XY11', 'XY11.Klinklang_73', 10 * retreat)

    async def test_bouffalant_needs_another(self):
        await self.check('Bouffalant + another', 'SV07.Bouffalant_119', 60,
                         target=self.filler, copies=2)
        await self.check('Bouffalant alone', 'SV07.Bouffalant_119', 0, target=self.filler)

    async def test_solgaleo_needs_lunala(self):
        await self.check('Solgaleo + Lunala', 'SM12.Solgaleo_142', 50, extra_p1=['SM12.Lunala_102'])
        await self.check('Solgaleo alone', 'SM12.Solgaleo_142', 0)

    async def test_stevens_carbink(self):
        await self.check("Carbink bench, Steven's active", 'SV10.StevensCarbink_86', 30,
                         target='SV10.StevensBeldum_143')
        await self.check("Carbink bench, other active", 'SV10.StevensCarbink_86', 0,
                         target=self.filler)

    async def test_tyrantrum(self):
        await self.check('Tyrantrum, equal Pokémon', 'SM6.Tyrantrum_69', 30, extra_p2=[self.filler])
        await self.check('Tyrantrum, more Pokémon', 'SM6.Tyrantrum_69', 0,
                         extra_p1=[self.filler, self.filler])


if __name__ == "__main__":
    unittest.main()
