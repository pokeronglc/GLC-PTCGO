"""Ancient Traits: every printing in the GLC card pool, through the real
action executor (t.play / t.attack / t.use), plus edge cases.

Traits live on the card definition's `passive` (no trait name in the text).
Pool printings (XY5, XY6, XY7, Promo_XY; no reprints elsewhere):
  Δ Evolution  XY6 Banette 32, Togekiss 46, Altaria 74, Unfezant 81;
               XYP Altaria 46, Fearow 57, Salamence 59
  α Growth     XY5 Swampert 36, Whiscash 41, Gorebyss 52, Kingdra 108; XYP Kingdra 39
  α Recovery   XY5 Ludicolo 37, Eelektrik 64, Tentacool 71, Azumarill 104, Bidoof 117
  Ω Barrage    XY5 Torchic 26, Nidoqueen 69, Medicham 81, Excadrill 97, Bunnelby 121
  Ω Barrier    XY5 Sceptile 9, Magcargo 24, Electrike 60, Rhyperior 77; XYP Regirock 49
  Δ Plus       XY6 Dustox 8, Articuno 17, Natu 28, Dragonite 52, Swellow 72
  θ Double     XY7 Vespiquen 11, Entei 15, Gyarados 21, Metagross 50; XYP Gyarados 60
  θ Stop       XY7 Volcarona 18, Baltoy 32, Golurk 35, Porygon-Z 67;
               XYP Malamar 58, Sableye 92, Celebi 93
θ Max / Δ Wild / Ω Barrier-EX etc. exist only on Pokémon-EX (Primal Kyogre,
M Rayquaza ...), which are not in the GLC pool and have no scripts.
"""
import unittest

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table, POISONED
from spirit.game.attributes import AttrID, PokemonTypes
from spirit.game.data_utils import def_for
from spirit.tools.effect_smoke import P1, P2

W, L, F, P = PokemonTypes.WATER, PokemonTypes.LIGHTNING, PokemonTypes.FIRE, PokemonTypes.PSYCHIC
G, M, Y, FI = PokemonTypes.GRASS, PokemonTypes.METAL, PokemonTypes.FAIRY, PokemonTypes.FIGHTING

WEEZING = 'SWSH2.GalarianWeezing_113'      # Active: opponent's Pokémon have no Abilities
POTION = 'BW1.Potion_100'
SPRAY = 'BW6.DevolutionSpray_113'
HAMMER = 'BW2.CrushingHammer_92'
CATCHER = 'BW2.PokmonCatcher_95'
LYSANDRE = 'XY2.Lysandre_90'
FLOAT, BAND, CHARM = 'BW9.FloatStone_99', 'XY1.MuscleBand_121', 'XY1.HardCharm_119'
ZUBAT, GOLBAT = 'ME4.Zubat_49', 'XY4.Golbat_32'   # Sneaky Bite: 2 counters on evolve

# (trait printing, non-trait printing of the same Pokémon, what it evolves from)
DELTA_EVOLUTION = [
    ('XY6.Altaria_74', 'XY6.Altaria_53', 'XY6.Swablu_73'),
    ('Promo_XY.Altaria_46', 'XY6.Altaria_53', 'XY6.Swablu_73'),
    ('Promo_XY.Fearow_57', 'XY6.Fearow_66', 'XY6.Spearow_65'),
    ('Promo_XY.Salamence_59', 'XY6.Salamence_57', 'XY6.Shelgon_56'),
    ('XY6.Banette_32', 'XY6.Banette_31', 'XY6.Shuppet_30'),
    ('XY6.Togekiss_46', 'XY6.Togekiss_45', 'XY6.Togetic_44'),
    ('XY6.Unfezant_81', 'XY6.Unfezant_80', 'XY6.Tranquill_79'),
]
ALPHA_GROWTH = ['XY5.Swampert_36', 'XY5.Whiscash_41', 'XY5.Gorebyss_52',
                'XY5.Kingdra_108', 'Promo_XY.Kingdra_39']
ALPHA_RECOVERY = ['XY5.Ludicolo_37', 'XY5.Eelektrik_64', 'XY5.Tentacool_71',
                  'XY5.Azumarill_104', 'XY5.Bidoof_117']
# (printing, attack, energy) -- attacks with no side requirements
OMEGA_BARRAGE = [('XY5.Torchic_26', 'Claw', [F]),
                 ('XY5.Nidoqueen_69', 'Poison Jab', [P]),
                 ('XY5.Medicham_81', 'Calm Mind', [FI, FI]),
                 ('XY5.Excadrill_97', 'Mach Claw', [M, M, M]),
                 ('XY5.Bunnelby_121', 'Burrow', [W])]
OMEGA_BARRIER = ['XY5.Sceptile_9', 'XY5.Magcargo_24', 'XY5.Electrike_60',
                 'XY5.Rhyperior_77', 'Promo_XY.Regirock_49']
# (printing, damaging attack, energy)
DELTA_PLUS = [('XY6.Dustox_8', 'Flap', [G]),
              ('XY6.Articuno_17', 'Tri Edge', [W, W, W]),
              ('XY6.Natu_28', 'Psywave', [P, P]),
              ('XY6.Dragonite_52', 'Heavy Impact', [G, G, G, L, L]),
              ('XY6.Swellow_72', 'Peck', [W, W])]
THETA_DOUBLE = ['XY7.Vespiquen_11', 'XY7.Entei_15', 'XY7.Gyarados_21',
                'XY7.Metagross_50', 'Promo_XY.Gyarados_60']
THETA_STOP = ['XY7.Volcarona_18', 'XY7.Baltoy_32', 'XY7.Golurk_35', 'XY7.PorygonZ_67',
              'Promo_XY.Malamar_58', 'Promo_XY.Sableye_92', 'Promo_XY.Celebi_93']


def _name(card):
    return def_for(card.archetype_id).display_name


class AncientTraitsFull(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    def table(self, lock=False, opp_hp=400):
        """P1 to act on turn 3.  lock=True: Galarian Weezing is P2's Active,
        so every P1 Pokémon has no Abilities (traits must keep working)."""
        t = Table(self)
        self.opp = t.put(WEEZING if lock else self.filler, P2, 'active')
        self._plain(self.opp, opp_hp)
        return t

    def _plain(self, pokemon, hp=400):
        pokemon.set_attribute(AttrID.WEAKNESS_TYPES, [])
        pokemon.set_attribute(AttrID.RESISTANCE_TYPES, [])
        pokemon.set_attribute(AttrID.HP, hp)

    def evo_targets(self, t, card, pid=P1):
        return t.targets(card, 'EvolvePokemonPlayAbility', pid)

    # ===================================================================
    # Δ Evolution: "You may play this card from your hand to evolve a
    # Pokémon during your first turn or the turn you play that Pokémon."
    # ===================================================================
    async def _delta_case(self, trait, plain, base, *, turn, fresh, lock=False):
        t = self.table(lock=lock)
        t.state.turn_number = turn
        mon = t.put(base, P1, 'active')
        if fresh:
            t.state.mark_entered_play(mon.entity_id)
        evo = t.put(trait, P1, 'hand')
        other = t.put(plain, P1, 'hand')
        return t, mon, evo, other

    async def test_delta_evolution_first_turn_going_first(self):
        for trait, plain, base in DELTA_EVOLUTION:
            with self.subTest(card=trait):
                t, mon, evo, other = await self._delta_case(trait, plain, base, turn=1, fresh=True)
                self.assertNotIn(mon.entity_id, self.evo_targets(t, other))
                self.assertIn(mon.entity_id, self.evo_targets(t, evo))
                await t.play(evo, targets=[mon.entity_id])
                self.assertIs(t.active(P1), evo)

    async def test_delta_evolution_first_turn_going_second(self):
        # Turn 2, P1 to act: P1 went second.  The Basic was placed at setup.
        for trait, plain, base in DELTA_EVOLUTION:
            with self.subTest(card=trait):
                t, mon, evo, other = await self._delta_case(trait, plain, base, turn=2, fresh=False)
                self.assertNotIn(mon.entity_id, self.evo_targets(t, other))
                await t.play(evo, targets=[mon.entity_id])
                self.assertIs(t.active(P1), evo)

    async def test_delta_evolution_turn_the_pokemon_was_played(self):
        for trait, plain, base in DELTA_EVOLUTION:
            with self.subTest(card=trait):
                t, mon, evo, other = await self._delta_case(trait, plain, base, turn=5, fresh=True)
                self.assertNotIn(mon.entity_id, self.evo_targets(t, other))
                await t.play(evo, targets=[mon.entity_id])
                self.assertIs(t.active(P1), evo)

    async def test_delta_evolution_benched_from_hand_same_turn(self):
        # Fully real: bench the Basic from hand, then evolve it at once.
        t = self.table()
        t.put(self.filler, P1, 'active')
        swablu = t.put('XY6.Swablu_73', P1, 'hand')
        await t.play(swablu)
        self.assertIn(swablu, t.zone(P1, 'bench'))
        plain = t.put('XY6.Altaria_53', P1, 'hand')
        self.assertNotIn(swablu.entity_id, self.evo_targets(t, plain))
        altaria = t.put('XY6.Altaria_74', P1, 'hand')
        await t.play(altaria, targets=[swablu.entity_id])
        self.assertIn(altaria, t.zone(P1, 'bench'))

    async def test_delta_evolution_survives_ability_lock(self):
        for trait, plain, base in DELTA_EVOLUTION:
            with self.subTest(card=trait):
                t, mon, evo, other = await self._delta_case(trait, plain, base, turn=5,
                                                            fresh=True, lock=True)
                self.assertIn(mon.entity_id, self.evo_targets(t, evo))
                self.assertNotIn(mon.entity_id, self.evo_targets(t, other))

    async def test_delta_evolution_after_devolution_spray(self):
        # House ruling (Oct 13): the Δ Evolution card may re-evolve a Pokémon
        # devolved this turn by Devolution Spray; other evolutions stay locked.
        for trait, plain, base in DELTA_EVOLUTION:
            with self.subTest(card=trait):
                t = self.table()
                mon = t.put(base, P1, 'active')
                evo = t.put(trait, P1, 'hand')
                await t.play(evo, targets=[mon.entity_id])         # evolved on turn 3
                self.assertIs(t.active(P1), evo)
                t.next_turn(); t.next_turn()                       # P1's turn 5
                spray = t.put(SPRAY, P1, 'hand')
                await t.play(spray)
                self.assertIs(t.active(P1), mon)
                self.assertIn(evo, t.zone(P1, 'hand'))
                other = t.put(plain, P1, 'hand')
                self.assertNotIn(mon.entity_id, self.evo_targets(t, other))
                self.assertIn(mon.entity_id, self.evo_targets(t, evo))
                await t.play(evo, targets=[mon.entity_id])
                self.assertIs(t.active(P1), evo)

    # FIXED Oct 13 (was: a Δ Evolution card already IN PLAY waives the evolution timing gates
    # for every Pokémon and every evolution card (bw_era _BWTextPassive.may_evolve_early
    # returns True for the trait text regardless of carrier; legal_actions
    # can_evolve_early / _DevolutionEvolutionLock consult all in-play passives).
    async def test_delta_evolution_in_play_does_not_help_other_cards(self):
        # The trait belongs to the evolution card being played.  An Altaria
        # with Δ Evolution already in play must not let a non-trait card
        # evolve a fresh Pokémon (nor lift a Devolution Spray lock).
        t = self.table()
        t.put('XY6.Altaria_74', P1, 'active')
        swablu = t.put('XY6.Swablu_73', P1, 'bench')
        t.state.mark_entered_play(swablu.entity_id)
        plain = t.put('XY6.Altaria_53', P1, 'hand')
        self.assertNotIn(swablu.entity_id, self.evo_targets(t, plain))
        t.state.turn_number = 1
        self.assertNotIn(swablu.entity_id, self.evo_targets(t, plain))

    # FIXED Oct 13 (was: a Δ Evolution card already IN PLAY waives the evolution timing gates
    # for every Pokémon and every evolution card (bw_era _BWTextPassive.may_evolve_early
    # returns True for the trait text regardless of carrier; legal_actions
    # can_evolve_early / _DevolutionEvolutionLock consult all in-play passives).
    async def test_delta_evolution_in_play_does_not_lift_spray_lock(self):
        t = self.table()
        t.put('XY6.Altaria_74', P1, 'bench')
        spearow = t.put('XY6.Spearow_65', P1, 'active')
        fearow = t.put('XY6.Fearow_66', P1, 'hand')
        await t.play(fearow, targets=[spearow.entity_id])
        t.next_turn(); t.next_turn()
        t.pokemon = lambda cands, prompt: fearow
        await t.play(t.put(SPRAY, P1, 'hand'))
        self.assertIs(t.active(P1), spearow)
        self.assertNotIn(spearow.entity_id, self.evo_targets(t, fearow))

    async def test_delta_evolution_does_not_beat_evolution_jammer(self):
        # Banette XY6 32 Evolution Jammer: "Your opponent can't play any
        # Pokémon from his or her hand to evolve ... during his or her next
        # turn."  Δ Evolution only waives timing; Jammer still stops it.
        t = self.table()
        t.put(self.filler, P1, 'active')
        swablu = t.put('XY6.Swablu_73', P1, 'bench')
        t.next_turn()                                    # P2's turn 4
        banette = t.put('XY6.Banette_32', P2, 'active')
        t.board.move_card(self.opp.entity_id, t.board.find_player_area(P2, 'bench').entity_id)
        t.energy(banette, P)
        await t.attack(banette, 'Evolution Jammer', pid=P2)
        if t.state.active_player_id != P1:
            t.next_turn()                                # P1's turn 5
        altaria = t.put('XY6.Altaria_74', P1, 'hand')
        self.assertNotIn(swablu.entity_id, self.evo_targets(t, altaria))

    # ===================================================================
    # α Growth: "When you attach an Energy card from your hand to this
    # Pokémon (except with an attack, Ability, or Trainer card), you may
    # attach 2 Energy cards."
    # ===================================================================
    async def test_alpha_growth_two_manual_attachments(self):
        for path in ALPHA_GROWTH:
            for lock in (False, True):
                with self.subTest(card=path, lock=lock):
                    t = self.table(lock=lock)
                    mon = t.put(path, P1, 'active')
                    bench = t.put(self.filler, P1, 'bench')
                    e1, e2, e3 = (t.put(t.basic_energy(k), P1, 'hand') for k in (W, L, W))
                    await t.play(e1, targets=[mon.entity_id])
                    self.assertIn(mon.entity_id, t.targets(e2, 'DefaultEnergyPlayAbility'))
                    self.assertNotIn(bench.entity_id, t.targets(e2, 'DefaultEnergyPlayAbility'))
                    await t.play(e2, targets=[mon.entity_id])
                    self.assertEqual({e1, e2}, set(t.board.attached_energies(mon)))
                    self.assertFalse(t.can(e3, 'DefaultEnergyPlayAbility'))

    async def test_alpha_growth_not_after_attaching_elsewhere(self):
        t = self.table()
        mon = t.put('XY5.Swampert_36', P1, 'active')
        bench = t.put(self.filler, P1, 'bench')
        e1, e2 = (t.put(t.basic_energy(W), P1, 'hand') for _ in range(2))
        await t.play(e1, targets=[bench.entity_id])
        self.assertFalse(t.can(e2, 'DefaultEnergyPlayAbility'))
        self.assertEqual([], t.board.attached_energies(mon))

    async def test_alpha_growth_only_on_the_trait_pokemon(self):
        # A non-trait Pokémon still gets one attachment per turn.
        t = self.table()
        t.put('XY5.Swampert_36', P1, 'bench')
        mon = t.put(self.filler, P1, 'active')
        e1, e2 = (t.put(t.basic_energy(W), P1, 'hand') for _ in range(2))
        await t.play(e1, targets=[mon.entity_id])
        self.assertFalse(t.can(e2, 'DefaultEnergyPlayAbility'))

    # ===================================================================
    # α Recovery: "When this Pokémon is healed, double the amount healed."
    # ===================================================================
    async def test_alpha_recovery_potion_doubles_and_caps(self):
        for path in ALPHA_RECOVERY:
            for lock in (False, True):
                with self.subTest(card=path, lock=lock):
                    t = self.table(lock=lock)
                    mon = t.put(path, P1, 'active')
                    full = t.hp(mon)
                    mon.set_attribute(AttrID.HP, full - 80)
                    t.pokemon = lambda cands, prompt: mon
                    await t.play(t.put(POTION, P1, 'hand'))
                    self.assertEqual(t.damage(mon), 20)          # 30 doubled = 60
                    await t.play(t.put(POTION, P1, 'hand'))
                    self.assertEqual(t.damage(mon), 0)           # capped at full HP
                    self.assertEqual(t.hp(mon), full)

    async def test_alpha_recovery_does_not_double_other_pokemon(self):
        t = self.table()
        t.put('XY5.Ludicolo_37', P1, 'active')
        other = t.put(self.filler, P1, 'bench')
        other.set_attribute(AttrID.HP, t.hp(other) - 80)
        t.pokemon = lambda cands, prompt: other
        await t.play(t.put(POTION, P1, 'hand'))
        self.assertEqual(t.damage(other), 50)

    async def test_alpha_recovery_attack_heal(self):
        # Swablu XY6 Bind Wound: "Heal 20 damage from 1 of your Pokémon."
        t = self.table()
        swablu = t.put('XY6.Swablu_73', P1, 'active')
        t.energy(swablu, W)
        mon = t.put('XY5.Bidoof_117', P1, 'bench')
        mon.set_attribute(AttrID.HP, t.hp(mon) - 50)
        t.pokemon = lambda cands, prompt: mon
        await t.attack(swablu, 'Bind Wound')
        self.assertEqual(t.damage(mon), 10)

    # ===================================================================
    # Ω Barrage: "This Pokémon may attack twice a turn. ..."
    # ===================================================================
    async def test_omega_barrage_attacks_twice_then_turn_ends(self):
        for path, attack, energy in OMEGA_BARRAGE:
            for lock in (False, True):
                with self.subTest(card=path, lock=lock):
                    t = self.table(lock=lock)
                    t.heads = True
                    mon = t.put(path, P1, 'active')
                    for k in energy:
                        t.energy(mon, k)
                    mon.set_attribute(AttrID.HP, t.hp(mon) - 30)      # for Calm Mind
                    self.assertFalse(await t.attack(mon, attack))     # turn goes on
                    self.assertEqual(t.state.active_player_id, P1)
                    self.assertIsNotNone(t.attack_offer(mon, attack))
                    # between the attacks nothing else may be played
                    item = t.put(self.item, P1, 'hand')
                    self.assertFalse(t.offers(item))
                    self.assertTrue(await t.attack(mon, attack))      # turn ends

    async def test_omega_barrage_second_attack_may_differ(self):
        t = self.table()
        mon = t.put('XY5.Medicham_81', P1, 'active')
        t.energy(mon, FI, 2)
        mon.set_attribute(AttrID.HP, t.hp(mon) - 30)
        self.assertFalse(await t.attack(mon, 'Calm Mind'))
        self.assertEqual(t.damage(mon), 0)
        hp = t.hp(self.opp)
        self.assertTrue(await t.attack(mon, 'Yoga Kick'))
        self.assertEqual(hp - t.hp(self.opp), 30)

    async def test_non_barrage_pokemon_attacks_once(self):
        t = self.table()
        mon = t.put('XY6.Swellow_72', P1, 'active')
        t.energy(mon, W, 2)
        self.assertTrue(await t.attack(mon, 'Peck'))

    # ===================================================================
    # Ω Barrier: "Whenever your opponent plays a Trainer card (excluding
    # Pokémon Tools and Stadium cards), prevent all effects of that card
    # done to this Pokémon."
    # ===================================================================
    def _barrier_table(self, path):
        t = self.table()
        t.next_turn()                                     # P2 to act
        p2 = t.active(P2)
        mine = t.put(path, P1, 'active')
        energy = t.energy(mine, W)
        bench_barrier = t.put(path, P1, 'bench')
        filler = t.put(self.filler, P1, 'bench')
        return t, p2, mine, energy, bench_barrier, filler

    async def test_omega_barrier_blocks_crushing_hammer(self):
        for path in OMEGA_BARRIER:
            with self.subTest(card=path):
                t, p2, mine, energy, *_ = self._barrier_table(path)
                hammer = t.put(HAMMER, P2, 'hand')
                await t.play(hammer, pid=P2)
                self.assertIn(hammer, t.zone(P2, 'discard'))
                self.assertIn(energy, t.board.attached_energies(mine))

    async def test_omega_barrier_blocks_gust_to_bench_target(self):
        for path in OMEGA_BARRIER:
            for gust in (LYSANDRE, CATCHER):
                with self.subTest(card=path, gust=gust):
                    t, p2, mine, energy, barrier, filler = self._barrier_table(path)
                    t.pokemon = lambda cands, prompt: barrier if barrier in cands else cands[0]
                    card = t.put(gust, P2, 'hand')
                    await t.play(card, pid=P2)
                    self.assertIn(card, t.zone(P2, 'discard'))
                    self.assertIn(barrier, t.zone(P1, 'bench'))
                    self.assertIs(t.active(P1), filler)        # the other target still works

    async def test_omega_barrier_own_trainers_still_work(self):
        for path in OMEGA_BARRIER:
            with self.subTest(card=path):
                t = self.table()
                mine = t.put(path, P1, 'active')
                mine.set_attribute(AttrID.HP, t.hp(mine) - 30)
                t.pokemon = lambda cands, prompt: mine
                await t.play(t.put(POTION, P1, 'hand'))
                self.assertEqual(t.damage(mine), 0)

    async def test_omega_barrier_survives_ability_lock(self):
        # P1's Galarian Weezing doesn't matter here: the lock must be on the
        # trait owner.  P2's Weezing Active locks P1; P2 then plays Hammer.
        t = self.table(lock=True)
        mine = t.put('XY5.Sceptile_9', P1, 'active')
        energy = t.energy(mine, G)
        t.next_turn()
        hammer = t.put(HAMMER, P2, 'hand')
        await t.play(hammer, pid=P2)
        self.assertIn(hammer, t.zone(P2, 'discard'))
        self.assertIn(energy, t.board.attached_energies(mine))

    async def test_omega_barrier_does_not_stop_other_pokemon_being_hit(self):
        t, p2, mine, energy, barrier, filler = self._barrier_table('XY5.Magcargo_24')
        e2 = t.energy(filler, W)
        t.board.move_card(mine.entity_id, t.board.find_player_area(P1, 'bench').entity_id)
        t.board.move_card(filler.entity_id, t.board.find_player_area(P1, 'activePokemonArea').entity_id)
        t.pokemon = lambda cands, prompt: filler if filler in cands else cands[0]
        t.picks = lambda cards, count, prompt, display: [e2] if e2 in cards else cards[:count]
        await t.play(t.put(HAMMER, P2, 'hand'), pid=P2)
        self.assertNotIn(e2, t.board.attached_energies(filler))

    # ===================================================================
    # Δ Plus: "If your opponent's Pokémon is Knocked Out by damage from an
    # attack of this Pokémon, take 1 more Prize card."
    # ===================================================================
    async def test_delta_plus_takes_extra_prize(self):
        for path, attack, energy in DELTA_PLUS:
            for lock in (False, True):
                with self.subTest(card=path, lock=lock):
                    t = self.table(lock=lock, opp_hp=10)
                    t.put(self.filler, P2, 'bench')
                    t.heads = True
                    mon = t.put(path, P1, 'active')
                    for k in energy:
                        t.energy(mon, k)
                    if path == 'XY6.Natu_28':
                        t.energy(self.opp, W)
                    before = len(t.zone(P1, 'prizes'))
                    await t.attack(mon, attack)
                    self.assertIn(self.opp, t.zone(P2, 'discard'))
                    self.assertEqual(len(t.zone(P1, 'prizes')), before - 2)

    async def test_delta_plus_benched_knockout(self):
        t = self.table()
        target = t.put(self.filler, P2, 'bench')
        self._plain(target, 50)
        mon = t.put('XY6.Dustox_8', P1, 'active')
        t.energy(mon, G, 3)
        t.pokemon = lambda cands, prompt: target
        before = len(t.zone(P1, 'prizes'))
        await t.attack(mon, 'Wind Shard')
        self.assertIn(target, t.zone(P2, 'discard'))
        self.assertEqual(len(t.zone(P1, 'prizes')), before - 2)

    async def test_delta_plus_not_for_poison_knockout(self):
        # Knocked Out by Poison between turns: not damage from an attack.
        t = self.table(opp_hp=10)
        t.put(self.filler, P2, 'bench')
        t.put('XY6.Swellow_72', P1, 'active')
        self.opp.set_attribute(AttrID.SPECIAL_CONDITIONS, [POISONED])
        before = len(t.zone(P1, 'prizes'))
        await t.checkup()
        self.assertIn(self.opp, t.zone(P2, 'discard'))
        self.assertEqual(len(t.zone(P1, 'prizes')), before - 1)

    async def test_delta_plus_not_for_other_attackers(self):
        # A Δ Plus Pokémon on the Bench gives nothing to another attacker.
        t = self.table(opp_hp=10)
        t.put(self.filler, P2, 'bench')
        t.put('XY6.Swellow_72', P1, 'bench')
        mon = t.put('XY6.Fearow_66', P1, 'active')     # no trait
        t.energy(mon, W)
        before = len(t.zone(P1, 'prizes'))
        await t.attack(mon, 'Peck')
        self.assertIn(self.opp, t.zone(P2, 'discard'))
        self.assertEqual(len(t.zone(P1, 'prizes')), before - 1)

    # ===================================================================
    # θ Double: "This Pokémon may have up to 2 Pokémon Tool cards attached
    # to it."
    # ===================================================================
    async def test_theta_double_two_tools(self):
        for path in THETA_DOUBLE:
            for lock in (False, True):
                with self.subTest(card=path, lock=lock):
                    t = self.table(lock=lock)
                    mon = t.put(path, P1, 'active')
                    plain = t.put(self.filler, P1, 'bench')
                    tools = [t.put(s, P1, 'hand') for s in (FLOAT, BAND, CHARM)]
                    await t.play(tools[0], targets=[mon.entity_id])
                    self.assertIn(mon.entity_id, t.targets(tools[1], 'DefaultToolPlayAbility'))
                    await t.play(tools[1], targets=[mon.entity_id])
                    self.assertIn(tools[0], t.attached(mon))
                    self.assertIn(tools[1], t.attached(mon))
                    targets = t.targets(tools[2], 'DefaultToolPlayAbility')
                    self.assertNotIn(mon.entity_id, targets)
                    self.assertIn(plain.entity_id, targets)
                    await t.play(tools[2], targets=[plain.entity_id])
                    self.assertFalse(t.targets(t.put(FLOAT, P1, 'hand'), 'DefaultToolPlayAbility'))

    # ===================================================================
    # θ Stop: "Prevent all effects of your opponent's Pokémon's Abilities
    # done to this Pokémon."
    # ===================================================================
    async def _sneaky_bite(self, path, lock=False):
        t = self.table(lock=lock)
        mine = t.put(path, P1, 'active')
        t.next_turn()
        zubat = t.put(ZUBAT, P2, 'bench')
        golbat = t.put(GOLBAT, P2, 'hand')
        t.pokemon = lambda cands, prompt: mine if mine in cands else cands[0]
        t.yes = True
        await t.play(golbat, pid=P2, targets=[zubat.entity_id])
        return t, mine, golbat

    async def test_theta_stop_blocks_opponent_ability_counters(self):
        for path in THETA_STOP:
            with self.subTest(card=path):
                t, mine, golbat = await self._sneaky_bite(path)
                self.assertIn(golbat, t.zone(P2, 'bench'))
                self.assertEqual(t.damage(mine), 0)

    async def test_theta_stop_survives_ability_lock(self):
        # Garbotoxin-style lock on the trait owner's side: P1 = trait owner;
        # use the Hex-style switch since Weezing would lock P2's Golbat.
        t = self.table()
        mine = t.put('XY7.Baltoy_32', P1, 'active')
        t.next_turn()
        t.state.abilities_disabled_through_turn = t.state.turn_number + 1
        zubat = t.put(ZUBAT, P2, 'bench')
        golbat = t.put(GOLBAT, P2, 'hand')
        t.pokemon = lambda cands, prompt: mine if mine in cands else cands[0]
        await t.play(golbat, pid=P2, targets=[zubat.entity_id])
        self.assertEqual(t.damage(mine), 0)

    async def test_sneaky_bite_hits_non_trait_pokemon(self):
        # Control: the same Ability damages a Pokémon without θ Stop.
        t = self.table()
        mine = t.put(self.filler, P1, 'active')
        t.next_turn()
        zubat = t.put(ZUBAT, P2, 'bench')
        golbat = t.put(GOLBAT, P2, 'hand')
        t.pokemon = lambda cands, prompt: mine if mine in cands else cands[0]
        await t.play(golbat, pid=P2, targets=[zubat.entity_id])
        self.assertEqual(t.damage(mine), 20)

    async def test_theta_stop_does_not_block_attacks(self):
        t = self.table()
        mine = t.put('Promo_XY.Sableye_92', P1, 'active')
        self._plain(mine, 70)
        t.next_turn()
        attacker = t.put('XY6.Swellow_72', P2, 'active')
        t.board.move_card(self.opp.entity_id, t.board.find_player_area(P2, 'bench').entity_id)
        t.energy(attacker, W, 2)
        await t.attack(attacker, 'Peck', pid=P2)
        self.assertEqual(t.damage(mine), 30)


if __name__ == '__main__':
    unittest.main()
