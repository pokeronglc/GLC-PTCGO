"""Antique Fossils' printed Abilities (they were missing): each works and
counts as "has an Ability"; the built-in Discard button does not."""
import unittest

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table
from spirit.game.attributes import AttrID, PokemonTypes
from spirit.game.card_effects.bw_era import _pokemon_has_ability
from spirit.game.data_utils import def_for
from spirit.game.session.effects import EffectContext
from spirit.tools.effect_smoke import P1, P2

D, M = PokemonTypes.DARKNESS, PokemonTypes.METAL
DOME, HELIX, AMBER = 'SV035.AntiqueDomeFossil_152', 'SV035.AntiqueHelixFossil_153', 'SV035.AntiqueOldAmber_154'
COVER, ROOT = 'SV07.AntiqueCoverFossil_129', 'SV07.AntiqueRootFossil_130'
JAW, SAIL = 'ME3.AntiqueJawFossil_68', 'ME3.AntiqueSailFossil_69'
PLUME, SKULL = 'RSV10PT5.AntiquePlumeFossil_79', 'ME5.AntiqueSkullFossil_73'
CROBAT, SABLEYE, DURALUDON = 'SWSH12.Crobat_105', 'SV2.Sableye_136', 'ME2.Duraludon_74'
GUZMA, ARTAZON = 'SM3.Guzma_115', 'SV2.Artazon_171'


class AntiqueFossilAbilities(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    async def fossil(self, t, spec, active=True):
        """Play the Fossil from hand (as a real player would), then make it
        the Active if asked."""
        t.put(self.filler, P1, 'active')
        card = t.put(spec, P1, 'hand')
        await t.play(card)
        fossil = next(p for p in t.board.pokemon_in_play(P1)
                      if def_for(p.archetype_id).display_name == def_for(card.archetype_id).display_name)
        if active:
            await t._run(lambda: EffectContext(t.session, P1, fossil, None).switch_active(P1, fossil))
            self.assertIs(t.active(P1), fossil)
        return fossil

    def attacker(self, t, spec, energy, count):
        old = t.active(P2)
        if old is not None:
            t.board.find_player_area(P2, 'activePokemonArea').remove_child(old)
        a = t.put(spec, P2, 'active')
        t.energy(a, energy, count)
        return a

    async def hit(self, t, attacker, title, target=None):
        t.next_turn()
        if target is not None:
            t.pokemon = lambda c, p: target if target in c else c[0]
        await t.attack(attacker, title, pid=P2)

    def test_all_count_as_having_an_ability(self):
        from spirit.game.models.board import create_card_entity
        from spirit.game.scripts.cards import loader
        for spec in (DOME, HELIX, AMBER, COVER, ROOT, JAW, SAIL, PLUME, SKULL):
            card = create_card_entity(loader.cards_by_guid[fixtures.definition(spec).guid.lower()], P2)
            with self.subTest(card=spec):
                self.assertTrue(_pokemon_has_ability(card))

    async def test_domed_armor(self):
        t = Table(self)
        fossil = await self.fossil(t, DOME)
        crobat = self.attacker(t, CROBAT, D, 1)
        await self.hit(t, crobat, 'Venomous Fang')
        self.assertEqual(t.damage(fossil), 20)

    async def test_helical_swell(self):
        for active, playable in ((True, False), (False, True)):
            t = Table(self)
            await self.fossil(t, HELIX, active=active)
            t.put(self.filler, P2, 'active')
            stadium = t.put(ARTAZON, P2, 'hand')
            t.next_turn()
            with self.subTest(active=active):
                self.assertEqual(t.can(stadium, 'DefaultStadiumPlayAbility', P2), playable)

    async def test_protective_cover(self):
        t = Table(self)
        fossil = await self.fossil(t, COVER)
        fossil.set_attribute(AttrID.HP, 200)            # survive the 70 so the Energy is visible
        energy = t.energy(fossil, PokemonTypes.DARKNESS)
        dura = self.attacker(t, DURALUDON, M, 3)
        await self.hit(t, dura, 'Hyper Beam')
        self.assertIn(energy, fossil.children)         # the effect is prevented
        self.assertEqual(200 - t.hp(fossil), 70)      # damage still lands

    async def test_primal_root(self):
        for active, offered in ((True, False), (False, True)):
            t = Table(self)
            await self.fossil(t, ROOT, active=active)
            sab = self.attacker(t, SABLEYE, D, 1)        # Unseen Claw costs exactly [D]
            t.next_turn()
            with self.subTest(active=active):
                self.assertEqual(t.attack_offer(sab, 'Unseen Claw', P2) is not None, offered)

    async def test_intimidating_jaw(self):
        t = Table(self)
        fossil = await self.fossil(t, JAW)
        crobat = self.attacker(t, CROBAT, D, 1)
        await self.hit(t, crobat, 'Venomous Fang')
        self.assertEqual(t.damage(fossil), 20)

    async def test_protective_sail_blocks_guzma(self):
        t = Table(self)
        fossil = await self.fossil(t, SAIL, active=False)
        t.put(self.filler, P2, 'active')
        t.put(self.filler, P2, 'bench')
        guzma = t.put(GUZMA, P2, 'hand')
        offered = []
        t.pokemon = lambda c, p: (offered.append(list(c)), c[0])[1]
        t.next_turn()
        await t.play(guzma, pid=P2)
        self.assertIsNot(t.active(P1), fossil)

    async def test_plume_protection(self):
        t = Table(self)
        fossil = await self.fossil(t, PLUME, active=False)
        crobat = self.attacker(t, CROBAT, D, 3)
        await self.hit(t, crobat, 'Critical Bite', target=fossil)
        self.assertEqual(t.damage(fossil), 0)

    async def test_spiny_skull(self):
        t = Table(self)
        await self.fossil(t, SKULL)
        crobat = self.attacker(t, CROBAT, D, 1)
        before = t.hp(crobat)
        await self.hit(t, crobat, 'Venomous Fang')
        self.assertEqual(before - t.hp(crobat), 30)

    async def test_amber_protection_blocks_cursed_eyes(self):
        t = Table(self)
        fossil = await self.fossil(t, AMBER, active=False)
        donor = t.active(P1)
        donor.set_attribute(AttrID.HP, t.hp(donor) - 50)
        t.put(self.filler, P2, 'active')
        absol = t.put('XY6.Absol_40', P2, 'hand')
        order = iter([donor, fossil])
        t.pokemon = lambda c, p: next((x for x in order if x in c), c[0])
        t.next_turn()
        await t.play(absol, pid=P2)
        self.assertEqual(t.damage(fossil), 0)


if __name__ == "__main__":
    unittest.main()
