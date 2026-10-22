"""Bug hunt 9: card text the engine silently ignores.

Found by differential audits (audits/results/silent_*.py): each clause was
run on a board where it is TRUE and one where it is FALSE (or a qualifying vs a
non-qualifying Pokémon) and the outcomes compared.  Every test below asserts the
PRINTED behaviour; the ones the engine gets wrong are expectedFailure + # BUG.
"""
import unittest

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table, PARALYZED
from tests.sweep_core import pay_cost
from spirit.game.attributes import AttrID, PokemonTypes
from spirit.game.data_utils import Attack, CARD_DEFS_BY_GUID, def_for
from spirit.tools.effect_smoke import P1, P2

TEDDIURSA = 'SWSH3.Teddiursa_138'     # Basic Colorless, Dig Claws [CC] 20, no text
LARVITAR = 'SWSH3.Larvitar_86'        # Basic Fighting, Pierce [CC] 20
CUFANT = 'SWSH3.Cufant_131'           # Basic Metal, Strength [MCC] 60
HITMONLEE = 'XY3.Hitmonlee_47'        # Basic, Stretch Kick: 30 to 1 Benched Pokémon
BOUNSWEET = 'SWSH3.Bounsweet_14'      # Basic Grass
TOGETIC = 'SM10.Togetic_137'          # Stage 1
EXP_SHARE = 'SWSH5.ExpShare_180'
WATER, FIRE, FIGHTING, LIGHTNING = (PokemonTypes.WATER, PokemonTypes.FIRE,
                                    PokemonTypes.FIGHTING, PokemonTypes.LIGHTNING)


def attack_of(spec, title):
    return next(a for a in fixtures.definition(spec).abilities
                if isinstance(a, Attack) and a.title == title)


class SilentIgnoreTests(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    # -- helpers ---------------------------------------------------------
    def mon(self, t, spec, pid=P1, zone='active', hp=400):
        p = t.put(spec, pid, zone)
        p.set_attribute(AttrID.WEAKNESS_TYPES, [])
        p.set_attribute(AttrID.RESISTANCE_TYPES, [])
        if hp is not None:
            p.set_attribute(AttrID.HP, hp)
        return p

    def board(self, spec, title, opp=None):
        t = Table(self)
        me = self.mon(t, spec)
        pay_cost(t, me, attack_of(spec, title))
        foe = self.mon(t, opp or self.filler, P2)
        return t, me, foe

    async def hit(self, t, me, title, foe):
        before = t.hp(foe)
        await t.attack(me, title)
        return before - t.hp(foe)

    async def taken_from_teddiursa(self, holder_spec, setup=None):
        """P2's vanilla Teddiursa (20 damage) attacks P1's Active `holder_spec`."""
        t = Table(self)
        holder = self.mon(t, holder_spec)
        if setup:
            setup(t, holder)
        ted = self.mon(t, TEDDIURSA, P2)
        t.energy(ted, WATER, 2)
        t.next_turn()
        before = t.hp(holder)
        await t.attack(ted, 'Dig Claws', pid=P2)
        return before - t.hp(holder)

    async def boosted(self, holder_spec, attacker_spec, title, kind):
        t = Table(self)
        att = self.mon(t, attacker_spec)
        t.energy(att, kind, sum(attack_of(attacker_spec, title).cost.values()))
        if holder_spec:
            self.mon(t, holder_spec, P1, 'bench')
        foe = self.mon(t, self.filler, P2)
        return await self.hit(t, att, title, foe)

    # ===================================================================
    # Root cause A: "If <condition>, this attack does nothing." — the BW/SV
    # interpreter (bw_era.bw_legacy_attack) only knows a handful of fixed
    # wordings; every other condition is skipped and full damage is done.
    # ===================================================================
    # FIXED Oct 13: Ting-Lu Arrogant Impact ignores "4 or more damage counters -> does nothing"
    async def test_tinglu_arrogant_impact_does_nothing_when_damaged(self):
        t, me, foe = self.board('SV4.TingLu_109', 'Arrogant Impact')
        # 4 counters below its real max HP (board() pads HP to 400, above max).
        me.set_attribute(AttrID.HP, t.hp(me) + t.damage(me) - 40)     # = max HP - 40
        self.assertEqual(await self.hit(t, me, 'Arrogant Impact', foe), 0)

    async def test_tinglu_arrogant_impact_hits_when_undamaged(self):
        t, me, foe = self.board('SV4.TingLu_109', 'Arrogant Impact')
        self.assertEqual(await self.hit(t, me, 'Arrogant Impact', foe), 220)

    # FIXED Oct 13: Medicham Seventh Kick ignores "don't have exactly 7 cards in hand -> nothing"
    async def test_medicham_seventh_kick_needs_seven_cards(self):
        t, me, foe = self.board('ME2PT5.Medicham_104', 'Seventh Kick')
        self.assertEqual(await self.hit(t, me, 'Seventh Kick', foe), 0)

    async def test_medicham_seventh_kick_with_seven_cards(self):
        t, me, foe = self.board('ME2PT5.Medicham_104', 'Seventh Kick')
        for _ in range(7):
            t.put(self.item, P1, 'hand')
        self.assertEqual(await self.hit(t, me, 'Seventh Kick', foe), 150)

    # FIXED Oct 13: Weavile Dark Penalty ignores "no Pokémon Tool attached -> nothing"
    async def test_weavile_dark_penalty_needs_tool_on_defender(self):
        t, me, foe = self.board('BW4.Weavile_70', 'Dark Penalty')
        self.assertEqual(await self.hit(t, me, 'Dark Penalty', foe), 0)

    # FIXED Oct 13: Oricorio Revelation Dance ignores "no Stadium in play -> nothing"
    async def test_oricorio_revelation_dance_needs_stadium(self):
        t, me, foe = self.board('Promo_SM.Oricorio_19', 'Revelation Dance')
        self.assertEqual(await self.hit(t, me, 'Revelation Dance', foe), 0)

    # FIXED Oct 13: Basculin Bared Fangs ignores "no damage counters before damage -> nothing"
    async def test_basculin_bared_fangs_needs_damaged_defender(self):
        t, me, foe = self.board('RSV10PT5.Basculin_24', 'Bared Fangs')
        self.assertEqual(await self.hit(t, me, 'Bared Fangs', foe), 0)

    # FIXED Oct 13: Eelektrik Small Appetite ignores "max HP 100 or more -> nothing"
    async def test_eelektrik_small_appetite_big_defender(self):
        t, me, foe = self.board('SM3.Eelektrik_45', 'Small Appetite')
        self.assertGreaterEqual(def_for(foe.archetype_id).extra_attributes[str(AttrID.HP.value)]['value'], 100)
        self.assertEqual(await self.hit(t, me, 'Small Appetite', foe), 0)

    # FIXED Oct 13: Vespiquen Commanding Queen ignores "4 or fewer Grass on Bench -> nothing"
    async def test_vespiquen_commanding_queen_needs_five_grass(self):
        t, me, foe = self.board('SM8.Vespiquen_32', 'Commanding Queen')
        self.assertEqual(await self.hit(t, me, 'Commanding Queen', foe), 0)

    # FIXED Oct 13: Mesprit Guardian Burst ignores "no Uxie and Azelf on Bench -> nothing"
    async def test_mesprit_guardian_burst_needs_uxie_and_azelf(self):
        t, me, foe = self.board('SV08.Mesprit_79', 'Guardian Burst')
        self.assertEqual(await self.hit(t, me, 'Guardian Burst', foe), 0)

    # FIXED Oct 13: Vikavolt Giga Railgun ignores "no Voltaic Lightning Energy -> nothing"
    async def test_vikavolt_giga_railgun_needs_voltaic_energy(self):
        t, me, foe = self.board('ME5.Vikavolt_26', 'Giga Railgun')
        self.assertEqual(await self.hit(t, me, 'Giga Railgun', foe), 0)

    # FIXED Oct 13: Sawk Rising Chop ignores "defender isn't a Pokémon ex -> nothing"
    async def test_sawk_rising_chop_needs_pokemon_ex(self):
        t, me, foe = self.board('RSV10PT5.Sawk_49', 'Rising Chop')
        self.assertEqual(await self.hit(t, me, 'Rising Chop', foe), 0)

    # FIXED Oct 13: Coalossal Tar Cannon ignores "fewer than 10 basic Fighting in discard -> nothing"
    async def test_coalossal_tar_cannon_needs_ten_fighting_in_discard(self):
        t, me, foe = self.board('ME2PT5.Coalossal_120', 'Tar Cannon')
        bench = self.mon(t, self.filler, P2, 'bench')
        before = t.hp(foe) + t.hp(bench)
        await t.attack(me, 'Tar Cannon')
        self.assertEqual(before - t.hp(foe) - t.hp(bench), 0)

    # ===================================================================
    # Root cause B: compound conditional body.  resolve_public_conditional_damage
    # gives up on "... N more damage and discard an Energy attached to the
    # Defending Pokémon" and the fallback drops the whole "If" sentence.
    # ===================================================================
    # FIXED Oct 13: Cacturne Payback: with 1 Prize left neither +60 nor the Energy discard happens
    async def test_cacturne_payback_one_prize_left(self):
        t, me, foe = self.board('BW9.Cacturne_10', 'Payback')
        t.energy(foe, WATER)
        t.set_prizes(P2, 1)
        self.assertEqual(await self.hit(t, me, 'Payback', foe), 90)
        self.assertEqual(len(t.board.attached_energies(foe)), 0)

    async def test_cacturne_payback_more_prizes(self):
        t, me, foe = self.board('BW9.Cacturne_10', 'Payback')
        t.energy(foe, WATER)
        self.assertEqual(await self.hit(t, me, 'Payback', foe), 30)
        self.assertEqual(len(t.board.attached_energies(foe)), 1)

    # ===================================================================
    # Root cause C: _attack_clause_allowed treats an UNKNOWN condition
    # (public_attack_condition -> None) as satisfied.
    # ===================================================================
    # FIXED Oct 13: Cryogonal First Freeze paralyzes on any turn ("you go second and it's your first turn" unknown -> allowed)
    async def test_cryogonal_first_freeze_not_on_later_turns(self):
        t, me, foe = self.board('SV3.Cryogonal_55', 'First Freeze')
        await t.attack(me, 'First Freeze')
        self.assertNotIn(PARALYZED, t.conditions(foe))

    # ===================================================================
    # Root cause D: effect bodies that run regardless of their "If" clause.
    # ===================================================================
    # FIXED Oct 13: Raticate Escaping Incisors switches even when the defender is a Basic
    async def test_raticate_escaping_incisors_no_switch_vs_basic(self):
        t, me, foe = self.board('SM10.Raticate_144', 'Escaping Incisors')
        self.mon(t, self.filler, P1, 'bench')
        await t.attack(me, 'Escaping Incisors')
        self.assertIs(t.active(P1), me)

    # FIXED Oct 13: Rhydon Dirty Work ignores "if you played Giovanni's Exile, discard 5 instead"
    async def test_rhydon_dirty_work_after_giovannis_exile(self):
        t, me, foe = self.board('SM10.Rhydon_94', 'Dirty Work')
        exile = fixtures.definition('SM10.GiovannisExile_174')
        t.state.trainers_played.append((exile.guid, exile.display_name, 2))
        self.assertEqual(def_for(exile.guid).display_name, "Giovanni's Exile")
        before = len(t.zone(P2, 'deck'))
        await t.attack(me, 'Dirty Work')
        self.assertEqual(before - len(t.zone(P2, 'deck')), 5)

    # ===================================================================
    # Root cause E: bw_era damage multiplier — the catch-all
    # `"benched pokémon" in subject -> per * len(my_bench)` swallows the
    # qualifier ("that has any damage counters on it", "that has any Fire
    # Energy attached", "that has 'Antique' in its name", "damage counter on
    # each of your Benched Pokémon").
    # ===================================================================
    # FIXED Oct 13: Seismitoad Tremulous Fist counts undamaged Benched Pokémon
    async def test_seismitoad_tremulous_fist_counts_only_damaged_bench(self):
        t, me, foe = self.board('SM12.Seismitoad_117', 'Tremulous Fist')
        self.mon(t, self.filler, P1, 'bench', hp=None)          # undamaged
        self.assertEqual(await self.hit(t, me, 'Tremulous Fist', foe), 80)

    # FIXED Oct 13: Armarouge Flame Legion counts Benched Pokémon without Fire Energy
    async def test_armarouge_flame_legion_counts_only_fire_bench(self):
        t, me, foe = self.board('ME5.Armarouge_12', 'Flame Legion')
        b = self.mon(t, self.filler, P1, 'bench')
        t.energy(b, WATER)
        self.assertEqual(await self.hit(t, me, 'Flame Legion', foe), 40)

    # FIXED Oct 13: Relicanth Fossil Beatdown counts non-"Antique" Benched Pokémon
    async def test_relicanth_fossil_beatdown_counts_only_antique(self):
        t, me, foe = self.board('ME5.Relicanth_17', 'Fossil Beatdown')
        self.mon(t, self.filler, P1, 'bench')
        self.assertEqual(await self.hit(t, me, 'Fossil Beatdown', foe), 10)

    # FIXED Oct 13: Gigalith Revenge Cannon counts Benched Pokémon instead of their damage counters
    async def test_gigalith_revenge_cannon_counts_bench_counters(self):
        t, me, foe = self.board('BW6.Gigalith_67', 'Revenge Cannon')
        b = self.mon(t, self.filler, P1, 'bench', hp=None)
        b.set_attribute(AttrID.HP, t.hp(b) - 30)                  # 3 counters
        self.assertEqual(await self.hit(t, me, 'Revenge Cannon', foe), 40)

    # ===================================================================
    # Root cause F: "1 of your <qualified> Pokémon" choices offer every
    # Pokémon on that side (qualifier dropped from the candidate list).
    # ===================================================================
    def record(self, t):
        seen = []
        t.pokemon = lambda c, p: (seen.append(list(c)), c[-1])[1]
        t.picks = lambda cards, n, p, d: (seen.append(list(cards)), list(cards)[:n])[1]
        return seen

    # FIXED Oct 13: Shaymin Send Flowers offers non-Grass Benched Pokémon
    async def test_shaymin_send_flowers_grass_only(self):
        t, me, foe = self.board('ME3.Shaymin_3', 'Send Flowers')
        self.mon(t, BOUNSWEET, P1, 'bench')
        other = self.mon(t, self.filler, P1, 'bench')
        t.deck(P1, [t.basic_energy(WATER)])
        seen = self.record(t)
        await t.attack(me, 'Send Flowers')
        self.assertFalse(any(other in c for c in seen))
        self.assertEqual(len(t.board.attached_energies(other)), 0)

    # FIXED Oct 13: Tatsugiri Mise en Place offers Evolution Pokémon ("1 of your Basic Pokémon")
    async def test_tatsugiri_mise_en_place_basic_only(self):
        t, me, foe = self.board('SV045.Tatsugiri_127', 'Mise en Place')
        evo = self.mon(t, TOGETIC, P1, 'bench')
        t.deck(P1, [t.basic_energy(WATER), t.basic_energy(WATER)])
        seen = self.record(t)
        await t.attack(me, 'Mise en Place')
        self.assertFalse(any(evo in c for c in seen))
        self.assertEqual(len(t.board.attached_energies(evo)), 0)

    # FIXED Oct 13: Mandibuzz Bone Sniper may target a Pokémon with no Special Energy
    async def test_mandibuzz_bone_sniper_special_energy_only(self):
        t, me, foe = self.board('ME5.Mandibuzz_50', 'Bone Sniper')
        special = next(d for d in CARD_DEFS_BY_GUID.values()
                       if type(d).__name__ == 'EnergyCardDef' and d.display_name == 'Aurora Energy')
        target = self.mon(t, self.filler, P2, 'bench')
        t.attach(special, target)
        seen = self.record(t)
        await t.attack(me, 'Bone Sniper')
        self.assertFalse(any(foe in c for c in seen))
        self.assertEqual(t.hp(foe), 400)

    # FIXED Oct 13: Mandibuzz Bone Drop may target a Pokémon without an Ability
    async def test_mandibuzz_bone_drop_ability_only(self):
        t, me, foe = self.board('XY10.Mandibuzz_58', 'Bone Drop')
        self.mon(t, 'SV2.Mimikyu_97', P2, 'bench')                # has an Ability
        seen = self.record(t)
        await t.attack(me, 'Bone Drop')
        self.assertFalse(any(foe in c for c in seen))
        self.assertEqual(t.hp(foe), 400)

    # ===================================================================
    # Root cause G: "If you have no cards in your hand, ignore all Energy in
    # this attack's cost" is not applied to the offer.
    # ===================================================================
    # FIXED Oct 13: Slowking Unarmed not offered with an empty hand and no Energy
    async def test_slowking_unarmed_free_with_empty_hand(self):
        t = Table(self)
        me = self.mon(t, 'SM3.Slowking_48')
        self.mon(t, self.filler, P2)
        self.assertEqual(t.zone(P1, 'hand'), [])
        self.assertIsNotNone(t.attack_offer(me, 'Unarmed'))

    # ===================================================================
    # Root cause H: standard_trainer_condition has no branch for "1 of your
    # Psychic Pokémon was Knocked Out during your opponent's last turn".
    # ===================================================================
    # FIXED Oct 13: Morty (SM8) playable without any Psychic Pokémon KO last turn
    async def test_morty_needs_psychic_ko(self):
        t = Table(self)
        self.mon(t, self.filler)
        self.mon(t, self.filler, P2)
        for _ in range(3):
            t.put(self.item, P2, 'hand')
        morty = t.put('SM8.Morty_186', P1, 'hand')
        self.assertFalse(t.can(morty, 'UseTrainerCard'))

    # ===================================================================
    # Root cause I: bw_era._BWTextPassive.prevents_damage — unknown attacker
    # qualifiers fall through to "prevent all damage" (so the Ability blocks
    # EVERY attacker).
    # ===================================================================
    # FIXED Oct 13: Mimikyu Safeguard ("from Pokémon ex and Pokémon V") blocks a plain Basic
    async def test_mimikyu_safeguard_only_ex_and_v(self):
        self.assertEqual(await self.taken_from_teddiursa('SV2.Mimikyu_97'), 20)

    # FIXED Oct 13: Aegislash SV4 ("from Pokémon ex and Pokémon V") blocks a plain Basic
    async def test_aegislash_only_ex_and_v(self):
        self.assertEqual(await self.taken_from_teddiursa('SV4.Aegislash_134'), 20)

    # FIXED Oct 13: Drednaw Impervious Shell ("if that damage is 200 or more") blocks 20 damage
    async def test_drednaw_impervious_shell_only_200_plus(self):
        self.assertEqual(await self.taken_from_teddiursa('SV07.Drednaw_44'), 20)

    # FIXED Oct 13: Mr. Mime SV035 ("same amount of Energy") blocks with unequal Energy
    async def test_mr_mime_same_energy_only(self):
        self.assertEqual(await self.taken_from_teddiursa('SV035.MrMime_122'), 20)

    # FIXED Oct 13: Bastiodon SM5 ("from Pokémon with Special Energy") blocks a basic-Energy attacker
    async def test_bastiodon_special_energy_attackers_only(self):
        self.assertEqual(await self.taken_from_teddiursa('SM5.Bastiodon_85'), 20)

    # FIXED Oct 13: Sceptile SM7 ("Grass-Energy Pokémon vs Ultra Beasts") blocks a non-UB with no Grass Energy
    async def test_sceptile_only_vs_ultra_beasts(self):
        self.assertEqual(await self.taken_from_teddiursa('SM7.Sceptile_10'), 20)

    async def test_pyroar_blocks_basic_attacker(self):       # control: a known qualifier works
        self.assertEqual(await self.taken_from_teddiursa('XY2.Pyroar_20'), 0)

    # Attack-granted shields: "During your opponent's next turn, prevent all
    # damage done to this Pokémon by attacks from <qualifier>" used to ignore
    # an unknown qualifier and block every attacker.
    async def shielded(self, spec, title, attacker=TEDDIURSA, attack='Dig Claws', kind=WATER):
        t = Table(self)
        me = self.mon(t, spec)
        pay_cost(t, me, attack_of(spec, title))
        foe = self.mon(t, attacker, P2)
        t.energy(foe, kind, sum(attack_of(attacker, attack).cost.values()))
        await t.attack(me, title)
        t.next_turn()
        before = t.hp(me)
        await t.attack(foe, attack, pid=P2)
        return before - t.hp(me)

    # FIXED Oct 13: Iron Moth SV065 Anachronism Repulsor ("from Ancient Pokémon") blocked a non-Ancient
    async def test_iron_moth_shield_not_vs_non_ancient(self):
        self.assertEqual(await self.shielded('SV065.IronMoth_9', 'Anachronism Repulsor'), 20)

    async def test_iron_moth_shield_vs_ancient(self):          # control
        self.assertEqual(await self.shielded('SV065.IronMoth_9', 'Anachronism Repulsor',
                                             'SV4.SlitherWing_107', 'Burning Turbulence', FIGHTING), 0)

    # FIXED Oct 13: Tentacruel SM9 Paranormal ("from Ultra Beasts") blocked a non-Ultra Beast
    async def test_tentacruel_paranormal_not_vs_non_ultra_beast(self):
        self.assertEqual(await self.shielded('SM9.Tentacruel_61', 'Paranormal'), 20)

    # ===================================================================
    # Root cause J: _BWTextPassive.modify_damage_dealt — "your <type/stage>
    # Pokémon's attacks" / "each of your Fighting Pokémon's attacks" is not
    # in the team-wide subject list, so only the holder's own attacks would be
    # boosted (and these holders' text never matches their own attacks).
    # ===================================================================
    # FIXED Oct 13: Machamp XY3 Fighting Fury boosts nothing
    async def test_machamp_fighting_fury_boosts_fighting(self):
        base = await self.boosted(None, LARVITAR, 'Pierce', FIGHTING)
        self.assertEqual(await self.boosted('XY3.Machamp_46', LARVITAR, 'Pierce', FIGHTING), base + 20)

    # FIXED Oct 13: Kingambit SV1 Leadership boosts nothing
    async def test_kingambit_leadership_boosts_basics(self):
        base = await self.boosted(None, TEDDIURSA, 'Dig Claws', WATER)
        self.assertEqual(await self.boosted('SV1.Kingambit_134', TEDDIURSA, 'Dig Claws', WATER), base + 30)

    # FIXED Oct 13: Dhelmise Promo_SM 53 Steelworker boosts nothing
    async def test_dhelmise_steelworker_boosts_metal(self):
        base = await self.boosted(None, CUFANT, 'Strength', PokemonTypes.METAL)
        self.assertEqual(await self.boosted('Promo_SM.Dhelmise_53', CUFANT, 'Strength', PokemonTypes.METAL), base + 10)

    async def test_perrserker_steely_spirit_control(self):   # control: dedicated helper works
        base = await self.boosted(None, CUFANT, 'Strength', PokemonTypes.METAL)
        self.assertEqual(await self.boosted('SWSH1.GalarianPerrserker_128', CUFANT, 'Strength', PokemonTypes.METAL), base + 20)

    # ===================================================================
    # Jirachi SV4 Stellar Veil: "Prevent all damage COUNTERS from being placed
    # ... by EFFECTS of attacks" — attack DAMAGE to the Bench is not an effect.
    # ===================================================================
    # FIXED Oct 13 (owner ruling): Stellar Veil also blocks Bench attack damage
    async def test_jirachi_stellar_veil_does_not_stop_bench_damage(self):
        t = Table(self)
        self.mon(t, self.filler)
        self.mon(t, 'SV4.Jirachi_126', P1, 'bench')
        target = self.mon(t, self.filler, P1, 'bench')
        lee = self.mon(t, HITMONLEE, P2)
        t.energy(lee, FIGHTING)
        t.next_turn()
        t.pokemon = lambda c, p: target if target in c else c[0]
        # Stretch Kick picks its target through the card browser.
        t.picks = lambda cards, n, p, d: [target] if target in cards else list(cards)[:n]
        await t.attack(lee, 'Stretch Kick', pid=P2)
        self.assertEqual(400 - t.hp(target), 30)

    async def test_jirachi_stellar_veil_blocks_bench_counters(self):   # control
        celebi = 'Promo_XY.Celebi_93'       # Sparkle Motion: 1 counter on each opposing Pokémon
        t = Table(self)
        active = self.mon(t, self.filler)
        jirachi = self.mon(t, 'SV4.Jirachi_126', P1, 'bench')
        other = self.mon(t, self.filler, P1, 'bench')
        c = self.mon(t, celebi, P2)
        pay_cost(t, c, attack_of(celebi, 'Sparkle Motion'))
        t.next_turn()
        await t.attack(c, 'Sparkle Motion', pid=P2)
        self.assertEqual([400 - t.hp(x) for x in (active, jirachi, other)], [10, 0, 0])


if __name__ == "__main__":
    unittest.main()
