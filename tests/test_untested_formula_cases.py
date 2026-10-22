"""Bug hunt (Oct 14) part 2b: the one-off damage wordings among the untested
Pokemon (those no family in test_untested_formula_sweep.py covers).

Each case: (card, attack, setup(t, me, opp) or None, expected damage to the
opponent's Active given the printed base `b`, label). Board: the attacker
with its cost paid and 300 HP, opponent Active 400 HP (no W/R), one opposing
Bench filler at 400 HP, coins heads unless the case says otherwise.
"""
import unittest
from unittest.mock import patch

from tests import test_hgss_rules as fixtures
from tests.test_untested_live_cards import Base, neutral, C, G, R, W, L, P, F, D, M, Y, P1, P2
from tests.untested_card_index import card
from spirit.game.attributes import AttrID, PokemonTypes
from spirit.game.session.effects import EffectContext


def bench(spec, n=1, pid=P1, hp=None):
    def f(t, me, opp):
        for _ in range(n):
            t.put(spec if '.' in spec else card(spec), pid, 'bench', hp=hp)
    return f


def discard(spec, n=1, pid=P1):
    def f(t, me, opp):
        for _ in range(n):
            t.put(spec if '.' in spec else card(spec), pid, 'discard')
    return f


def energy_on(who, kind, n=1):
    def f(t, me, opp):
        target = {'me': me, 'opp': opp, 'oppbench': t.opp_bench}[who]
        t.energy(target, kind, n)
    return f


def both(*fs):
    def f(t, me, opp):
        for g in fs:
            g(t, me, opp)
    return f


def hp(who, value):
    def f(t, me, opp):
        {'me': me, 'opp': opp}[who].set_attribute(AttrID.HP, value)
    return f


def prizes(pid, n):
    return lambda t, me, opp: t.set_prizes(pid, n)


CASES = [
    ('BW5.Heatmor_19', 'Hot Lick', None, lambda b: b, 'not Durant'),
    ('SM9.Zoroark_91', 'Night Punishment', discard('BW1.Basculin_35', 3), lambda b: 60, '3 in discard'),
    ('SV10.Abomasnow_60', None, energy_on('me', G, 2), lambda b: b + 120, '2+ grass'),
    ('XY3.Accelgor_9', None, None, lambda b: b, 'not evolved this turn'),
    ('SM4.Aggron_67', None, bench('BW1.Basculin_35', 2, hp=None), lambda b: b, 'undamaged bench'),
    ('SM6.AlolanMarowak_12', None, bench('PGO.AlolanRaticate_42', 1), lambda b: 40, '2 Alolan'),
    ('SM12.AlolanNinetales_145', 'Rubbish Blizzard', discard('SV065.Powerglass_63', 2), lambda b: 20, '2 tools'),
    ('SWSH7.Appletun_121', None, lambda t, me, opp: t.attach('BW6.BlendEnergyGrassFirePsychicDarkness_117', opp), lambda b: 70, '1 special'),
    ('SM12.Armaldo_112', None, discard('Unidentified Fossil', 2), lambda b: b + 100, '2 fossils'),
    ('ME5.Armarouge_12', None, both(bench('BW1.Basculin_35', 1), lambda t, me, opp: t.energy(t.zone(P1, 'bench')[-1], R, 1)),
     lambda b: b + 40, '1 fire bench'),
    ('ME2PT5.Beautifly_13', None, lambda t, me, opp: [t.put(t.basic_energy(D), P2, 'hand') for _ in range(2)],
     lambda b: 160, '2 energy in hand'),
    ('SM9.Bisharp_105', None, None, lambda b: b + 90, 'no counters'),
    ('SM9.Bisharp_105', None, hp('me', 290), lambda b: b, 'damaged'),
    ('SWSH1.Bisharp_134', None, bench('Pawniard', 2), lambda b: b + 60, '2 Pawniard'),
    ('SWSH10.Bisharp_116', None, bench('Pawniard', 1, hp=20), lambda b, t, me, opp: b + 30 * (t.damage(t.zone(P1, 'bench')[0]) // 10), 'pawniard counters'),
    ('ME2.Bronzong_72', None, lambda t, me, opp: [t.board.attach_card(t.put('SV065.Powerglass_63', w.owning_player_id, 'hand').entity_id, w.entity_id) for w in (me, opp)], lambda b: 80, '2 tools'),
    ('XY8.Bronzor_95', None, prizes(P2, 1), lambda b: b + 60, '1 prize left'),
    ('XY8.Bronzor_95', None, prizes(P2, 2), lambda b: b, '2 prizes left'),
    ('BW9.Cacturne_10', None, prizes(P2, 1), lambda b: b + 60, '1 prize left'),
    ('XY11.Chandelure_50', None, discard('SV4.Tulip_181', 3), lambda b: b + 30, '3 supporters'),
    ('Promo_SWSH.Charizard_66', None, discard('Leon', 2), lambda b: b + 100, '2 Leon'),
    ('TwentiethAnn.Charmander_103', None, hp('me', 270), lambda b: 60, '3 counters, heads'),
    ('SWSH9.Claydol_59', None, bench('BW1.Basculin_35', 1), lambda b: b + 90, 'same bench count'),
    ('SWSH9.Claydol_59', None, bench('BW1.Basculin_35', 2), lambda b: b, 'different bench count'),
    ('SWSH11.Clefairy_62', None, energy_on('me', P, 1), lambda b, t, me, opp: 20 * sum(1 for c in me.children if PokemonTypes.PSYCHIC.value in (c.get_attribute(AttrID.ENERGY_INFO) or {}).get('options', [[None]])[0]), 'psychic on me'),
    ('SM10.Crabominable_105', None, bench('BW1.Basculin_35', 1, pid=P2), lambda b: b + 100, '2 fewer (1 vs 3)'),
    ('SM3.Darkrai_87', None, lambda t, me, opp: t.state.gx_used.add(P2), lambda b: b + 80, 'opp used GX'),
    ('SM3.Darkrai_87', None, None, lambda b: b, 'opp has not used GX'),
    ('MEP.Delphox_74', None, energy_on('opp', D, 2), lambda b, t, me, opp: 30 * (len([c for c in me.children]) + 2), 'energy all'),
    ('SWSH12.Delphox_27', None, discard('Serena', 2), lambda b: 120, '2 Serena'),
    ('CZ.Deoxys_172', None, lambda t, me, opp: t.attach('Fusion Strike Energy' and card('Fusion Strike Energy'), me),
     lambda b: b + 80, 'fusion strike energy'),
    ('SV07.Diancie_86', None, lambda t, me, opp: t.attach('BW6.BlendEnergyGrassFirePsychicDarkness_117', t.opp_bench),
     lambda b: 40, '1 special on bench'),
    ('SV045.Dondozo_126', None, discard('Tatsugiri', 2), lambda b: 100, '2 Tatsugiri'),
    ('SM7.Donphan_73', None, hp('me', 260), lambda b: 40, '4 counters'),
    ('SV05.Drampa_138', None, bench('BW1.Basculin_35', 2, hp=10), lambda b: b + 120, 'all bench damaged'),
    ('SV05.Drampa_138', None, both(bench('BW1.Basculin_35', 1, hp=10), bench('BW1.Basculin_35', 1)), lambda b: b, 'one undamaged'),
    ('BW6.Drifblim_51', None, discard('BW6.BlendEnergyGrassFirePsychicDarkness_117', 2, pid=P2), lambda b: 100, '2 specials'),
    ('XY10.Duosion_34', None, bench('Solosis', 1), lambda b: b + 30, 'Solosis'),
    ('Promo_SM.DuskManeNecrozma_107', None, prizes(P2, 1), lambda b: b + 100, '1 prize'),
    ('SM5.Eevee_105', None, both(bench('BW1.Basculin_35', 1), bench('BW1.Zekrom_114', 1)), lambda b: 20, '2 types'),
    ('BW3.Emolga_37', None, bench('BW1.Zekrom_114', 1), lambda b: b + 20, 'lightning bench'),
    ('BW5.Empoleon_29', None, None, lambda b: 30, '3 in play'),
    ('BW11.Empoleon_35', None, hp('me', 100), lambda b: b + 60, 'fewer HP'),
    ('BW11.Empoleon_35', None, hp('opp', 200), lambda b: b + 200, 'more HP (opp already at 200)'),
    ('SM5.Empoleon_34', None, bench('BW1.Basculin_35', 1), lambda b: 40, '2 benched total'),
    ('ME2PT5.ErikasVictreebel_6', None, None, lambda b: 40, 'only itself'),
    ('SV10.EthansTyphlosion_190', None, None, lambda b: b, 'no adventure cards'),
    ('CZ.Exeggutor_58', None, lambda t, me, opp: t.energy(t.put('BW1.Basculin_35', P1, 'bench'), D, 2),
     lambda b, t, me, opp: 20 * (len(me.children) + 2), 'energy all mine'),
    ('XY6.Exeggutor_2', None, None, lambda b: 40, '2 colorless fillers'),
    ('SWSH2.Falinks_109', None, bench('SWSH2.Falinks_109', 2), lambda b: 60, '2 Falinks on bench'),
    ('SV06.Farigiraf_84', None, bench('SM12.Prinplup_55', 1), lambda b: 80, '2 stage 1'),
    ('DM.Feraligatr_24', None, discard('BW1.Basculin_35', 0), lambda b: b, 'no water in discard'),
    ('SWSH4.Garbodor_111', None, discard('SV065.Powerglass_63', 2), lambda b: 60, '2 tools in discard'),
    ('BW8.Garbodor_67', None, lambda t, me, opp: opp.set_attribute(AttrID.RETREAT_COST, 3), lambda b: 60, 'retreat 3'),
    ('HF.Garchomp_140', None, lambda t, me, opp: t.state.trainers_played.append(('x', 'Cynthia', 2)),
     lambda b: b + 100, 'Cynthia played'),
    ('HF.Garchomp_140', None, None, lambda b: b, 'no Cynthia'),
    ('SWSH12.Glalie_42', None, None, lambda b: b, 'no Candice'),
    ('SWSH8.Grimmsnarl_178', None, bench('BW1.Basculin_35', 2), lambda b: b + 140, '2 benched'),
    ('SWSH8.Grimmsnarl_178', None, bench('BW1.Basculin_35', 3), lambda b: b, '3 benched'),
    ('SM7.Grumpig_60', None, None, lambda b: b, 'no shared names'),
    ('Promo_SM.Gumshoos_97', None, lambda t, me, opp: t.put('BW1.Basculin_35', P2, 'hand'), lambda b: b + 80, 'Pokemon in hand'),
    ('Promo_SM.Gumshoos_97', None, lambda t, me, opp: t.put(self_item(t), P2, 'hand'), lambda b: b, 'no Pokemon'),
    ('SM3.Gyarados_33', None, discard('Magikarp', 3), lambda b: 150, '3 Magikarp'),
    ('BW11.Gyarados_31', None, both(prizes(P1, 5), prizes(P2, 4)), lambda b: 60, '3 taken'),
    ('DV.Haxorus_16', None, None, lambda b: b + 60, 'Colorless filler'),
    ('SM8.Heracross_18', None, bench('SM12.Empoleon_56', 1), lambda b: b + 90, 'stage 2 bench'),
    ('SWSH10.HisuianOverqwil_91', None, energy_on('me', D, 3), lambda b: b + 90, '3+ darkness'),
    ('SV045.Houndstone_168', None, discard('SV4.Espathra_81', 2), lambda b: b + 20, '2 psychic'),
    ('SWSH5.Jellicent_42', None, lambda t, me, opp: [t.put(t.basic_energy(W), P1, 'discard') for _ in range(3)], lambda b: 30, '3 water'),
    ('XY11.Jumpluff_5', None, prizes(P1, 4), lambda b: 80, '4 prizes'),
    ('SWSH12.Keldeo_46', None, both(bench('Cobalion'), bench('Terrakion'), bench('Virizion')), lambda b: b + 170, 'trio'),
    ('SWSH12.Keldeo_46', None, both(bench('Cobalion'), bench('Terrakion')), lambda b: b, 'missing one'),
    ('SV3.Kingambit_150', None, hp('opp', 360), lambda b, t, me, opp: 400 - t.hp(opp) if opp in t.zone(P2, 'discard') else -1, '4 counters -> KO'),
    ('SV3.Kingambit_150', None, hp('opp', 370), lambda b, t, me, opp: 30 if opp not in t.zone(P2, 'discard') else -1, '3 counters -> no KO'),
    ('DM.Kommoo_54', None, hp('me', 220), lambda b: b + 120, '8 counters'),
    ('SM4.Kommoo_77', None, bench('BW1.Basculin_35', 2, pid=P2), lambda b: b + 90, 'fewer in play'),
    ('SM1.Krookodile_85', None, lambda t, me, opp: [t.put(self_item(t), P2, 'hand') for _ in range(3)], lambda b: b + 60, '3 cards'),
    ('BW5.Krookodile_66', None, prizes(P1, 4), lambda b: 80, '2 taken'),
    ('SM8.Larvitar_115', None, hp('opp', 370), lambda b: b + 70 + 30, '3 counters'),
    ('XY10.Lucario_63', None, bench('BW1.Basculin_35', 1, pid=P2), lambda b: b + 120, '2 fewer'),
    ('SM8.Xatu_88', 'Energy Gaze', lambda t, me, opp: t.put(t.basic_energy(D), P2, 'hand'), lambda b: b + 60, 'energy in hand'),
    ('SM8.Xatu_88', 'Energy Gaze', None, lambda b: b, 'no energy'),
    ('Promo_SM.Gumshoos_97', None, lambda t, me, opp: t.put('BW1.Basculin_35', P2, 'hand'), lambda b: b + 80, 'pokemon'),
    ('SM7.Ludicolo_38', None, None, lambda b: b + 20, '2 others'),
    ('ME55.Lunala_80', None, lambda t, me, opp: [t.put(t.basic_energy(D), P1, 'discard') for _ in range(2)], lambda b: b + 40, '2 energy'),
    ('XY2.Luxio_33', None, prizes(P2, 4), lambda b: 80, '2 taken by opponent'),
    ('Promo_SWSH.Machamp_53', None, discard('BW1.Basculin_35', 2), lambda b: 0, 'no fighting'),
    ('BW10.Machoke_48', None, hp('me', 10), lambda b: b + 70, 'hp 10'),
    ('Promo_XY.Magearna_165', None, bench('BW1.Zekrom_114', 1, pid=P2), lambda b: 40, '2 types on opp bench'),
    ('PGO.Magikarp_21', None, discard('Magikarp', 2), lambda b: b + 60, '2 magikarp'),
    ('BW2.Mandibuzz_69', 'Dark Pulse' if False else None, None, None, ''),
    ('BW1.Mandibuzz_73', None, None, lambda b: b, 'basic defender'),
    ('SV07.Marowak_73', None, bench('Cubone', 1, hp=10), lambda b: b + 120, 'damaged cubone'),
    ('SV07.Marowak_73', None, bench('Cubone', 1), lambda b: b, 'healthy cubone'),
    ('BW6.Marowak_61', None, lambda t, me, opp: opp.set_attribute(AttrID.RESISTANCE_TYPES, [W.value]), lambda b: b + 30, 'resistance'),
    ('SV045.Maushold_210', None, bench('SV045.Maushold_210', 1), lambda b: 140, '2 Maushold'),
    ('SM11.Medicham_110', None, lambda t, me, opp: t.board.attach_card(t.put('Karate Belt' and card('Karate Belt'), P1, 'hand').entity_id, me.entity_id),
     lambda b: b + 60, 'Karate Belt'),
    ('SM7.Medicham_77', None, hp('me', 30), lambda b: b + 160, '30 HP'),
    ('SV09.Metagross_63', None, both(bench('Beldum'), bench('Metang')), lambda b: b + 150, 'both'),
    ('SV09.Metagross_63', None, bench('Beldum'), lambda b: b, 'only Beldum'),
    ('XY2.Miltank_83', None, bench('SM12.Empoleon_56'), lambda b: b + 70, 'stage 2'),
    ('SWSH5.Morpeko_98', None, None, lambda b: b + 90, 'empty hand'),
    ('SWSH5.Morpeko_98', None, lambda t, me, opp: t.put(self_item(t), P1, 'hand'), lambda b: b, '1 card'),
    ('BW9.Nidoking_58', None, bench('Nidoqueen', 2), lambda b: b + 80, '2 Nidoqueen'),
    ('BW9.Noctowl_92', None, lambda t, me, opp: [t.put(self_item(t), P2, 'hand') for _ in range(3)], lambda b: 30, '3 cards'),
    ('SV4.Orbeetle_12', None, lambda t, me, opp: [t.put(t.basic_energy(D), P2, 'discard') for _ in range(2)], lambda b: 60, '2 energy'),
    ('SV08.Palkia_136', None, None, lambda b, t, me, opp: 40 * len(me.children), 'basic energy on it'),
    ('ME2PT5.Pangoro_140', None, bench('Pancham', 1, hp=10), lambda b: b + 120, 'damaged pancham'),
    ('XY11.Pawniard_63', None, bench('Pawniard', 1), lambda b: 20, '2 Pawniard'),
    ('HF.Pheromosa_105', None, prizes(P1, 1), lambda b: b + 90, '1 prize'),
    ('SM11.Poipole_102', None, both(prizes(P1, 1), prizes(P2, 1)), lambda b: b + 130, 'both 1'),
    ('SM10.Poliwrath_39', None, both(bench('Poliwag'), bench('Poliwhirl')), lambda b: b + 90, 'both'),
    ('XY11.Primeape_53', None, None, lambda b: b + 60, 'opp has more HP'),
    ('XY11.Primeape_53', None, hp('opp', 200), lambda b: b + 200, 'opp has less HP (already at 200)'),
    ('SM7.Swalot_58', None, hp('opp', 200), lambda b: b + 80 + 200, 'opp has less HP (already at 200)'),
    ('SM7.Swalot_58', None, None, lambda b: b, 'opp has more HP'),
    ('SM6.Pyroar_19', None, lambda t, me, opp: t.stadium(card('Lysandre Labs'), P2), lambda b: b + 60, 'Lysandre Labs'),
    ('TwentiethAnn.Raichu_109', None, bench('BW1.Basculin_35', 2), lambda b: 40, '2 benched'),
    ('SWSH11.Raichu_53', None, lambda t, me, opp: t.state.vstar_used.add(P1), lambda b: b + 120, 'vstar used'),
    ('SWSH12.Raichu_50', None, lambda t, me, opp: t.state.vstar_used.add(P2), lambda b: b + 100, 'opp vstar used'),
    ('ME1.Raikou_48', None, energy_on('me', L, 4), lambda b: b + 90, '4 lightning'),
    ('XY12.Raticate_67', None, discard('BW6.BlendEnergyGrassFirePsychicDarkness_117', 2, pid=P2), lambda b: 120, '2 specials'),
    ('SM7.Registeel_96', None, None, lambda b: b, 'no ability'),
    ('SL.Reshiram_14', None, hp('me', 270), lambda b: b + 30, '3 counters'),
    ('BW11.Reuniclus_76', None, bench('Reuniclus', 1), lambda b: 80, '2 Reuniclus'),
    ('BW8.Rotom_49', None, lambda t, me, opp: [t.put(self_item(t), P2, 'hand') for _ in range(2)], lambda b: 40, '2 trainers'),
    ('XY6.Salamence_57', None, lambda t, me, opp: [t.put(self_item(t), P2, 'hand') for _ in range(3)], lambda b: 60, '3 cards'),
    ('BW6.Sawk_69', None, hp('me', 270), lambda b: 40, '3 counters'),
    ('BW1.Sawsbuck_14', None, both(energy_on('me', G, 1), energy_on('opp', G, 1)), lambda b, t, me, opp: b + 10 * (1 + 1 + sum(1 for c in me.children[:-1] if 'Grass' in str(c.get_attribute(AttrID.NAME)))), 'grass both'),
    ('BW4.Scrafty_74', None, None, lambda b: b + 30, 'fewer HP'),
    ('SWSH35.Scrafty_42', None, lambda t, me, opp: t.state.trainers_played.append(('x', 'Piers', 2)), lambda b: b + 90, 'Piers'),
    ('SM10.Sharpedo_111', None, energy_on('me', D, 2), lambda b, t, me, opp: b + 20 * sum(1 for c in me.children if (c.get_attribute(AttrID.ENERGY_INFO) or {}).get('options') == [[D.value]]), 'darkness'),
    ('ME1.Shedinja_144', None, hp('opp', 370), lambda b: 60 + 30, '3 counters (already on)'),
    ('XY6.Shedinja_11', None, hp('me', 280), lambda b: 100, '2 counters'),
    ('XY2.Shiftry_7', None, bench('BW1.Basculin_35', 1), lambda b: 40, '2 benched both sides'),
    ('SWSH3.Shiinotic_80', None, lambda t, me, opp: t.stadium(card('Glimwood Tangle'), P2), lambda b: b + 60, 'Glimwood Tangle'),
    ('Promo_SM.ShiningLugia_82', None, None, lambda b: b, 'no ability'),
    ('SM2.Slowbro_49', None, lambda t, me, opp: me.set_attribute(AttrID.SPECIAL_CONDITIONS, ['Poisoned']), lambda b: b + 80, 'poisoned'),
    ('SM2.Slowbro_49', None, None, lambda b: b, 'healthy'),
    ('SWSH11.Spiritomb_117', None, discard('Spiritomb', 2), lambda b: b + 120, '2 Spiritomb'),
    ('XY5.Starmie_73', None, lambda t, me, opp: t.energy(opp, D, len(me.children)), lambda b: b + 60, 'same energy'),
    ('SWSH2.Stonjourner_111', None, energy_on('me', F, 1), lambda b: b + 60, 'extra energy'),
    ('SWSH2.Stonjourner_111', None, None, lambda b: b, 'exact cost'),
    ('SM11.Stunfisk_67', None, None, lambda b: b + 30, 'opp has more HP'),
    ('XY4.Swalot_38', None, hp('opp', 200), lambda b: b + 50 + 200, 'opp fewer HP'),
    ('SM10.Snorlax_158', None, None, lambda b: b, 'not TAG TEAM'),
    ('TATM.TeamMagmasZangoose_22', None, None, lambda b: 0, 'no Team Magma bench'),
    ('ME2PT5.TeamRocketsSpidops_19', None, None, lambda b: 30, 'itself'),
    ('SV10.TeamRocketsPorygonZ_155', None, None, lambda b: 0, 'none in discard'),
    ('SM10.Tentacool_40', None, lambda t, me, opp: t.state.trainers_played.append(('x', 'Janine', 2)), lambda b: b + 50, 'Janine'),
    ('SV045.Toxtricity_141', None, both(bench('BW1.Basculin_35'), bench('BW1.Zekrom_114')), lambda b: b + 60, '2 types'),
    ('BW8.Trubbish_65', None, lambda t, me, opp: [t.board.attach_card(t.put('SV065.Powerglass_63', w.owning_player_id, 'hand').entity_id, w.entity_id) for w in (me, opp)], lambda b: 40, '2 tools'),
    ('SM3.Tynamo_44', None, energy_on('opp', W, 1), lambda b: b + 30, 'water on opp'),
    ('PGO.Tyranitar_43', None, bench('BW1.Basculin_35', 1, hp=30), lambda b, t, me, opp: 10 * (t.damage(t.zone(P1, 'bench')[0]) // 10), 'bench counters'),
    ('BW8.Vespiquen_5', None, hp('opp', 370), lambda b: 60 + 30, '3 counters (already on)'),
    ('SV05.Vikavolt_56', None, bench('Charjabug', 2), lambda b: b + 160, '2 Charjabug'),
    ('XY7.Virizion_12', None, prizes(P2, 4), lambda b: b + 80, 'more prizes left'),
    ('SWSH12.Virizion_14', None, both(bench('Cobalion'), bench('Terrakion'), bench('Keldeo')), lambda b: b + 70, 'trio'),
    ('SWSH6.Weezing_95', None, None, lambda b, t, me, opp: b + 20 * sum(1 for c in me.children if (c.get_attribute(AttrID.ENERGY_INFO) or {}).get('options') == [[D.value]]), 'darkness'),
    ('SM4.Wigglytuff_72', None, energy_on('oppbench', D, 1), lambda b: b + 60, 'darkness on opp bench'),
    ('Promo_XY.Xerneas_31', None, bench('Yveltal', 1, pid=P2), lambda b: b + 40, 'Yveltal'),
    ('Promo_XY.Yveltal_32', None, bench('Xerneas', 1, pid=P2), lambda b: b + 40, 'Xerneas'),
    ('SM9.Zebstrika_45', None, None, lambda b: b, 'not evolved'),
    ('BW11.Zoroark_90', None, None, lambda b, t, me, opp: 20 * sum(1 for p in t.board.pokemon_in_play(P1) if D.value in (p.get_attribute(AttrID.POKEMON_TYPES) or [])), 'darkness in play'),
]


def self_item(t):
    return t.test.item


class FormulaCases(Base):
    async def test_cases(self):
        bad, checked = [], 0
        for ref, title, setup, expect, label in CASES:
            if expect is None:
                continue
            d = fixtures.definition(ref)
            attacks = [a for a in d.abilities if type(a).__name__ == 'Attack']
            atk = next(a for a in attacks if a.title == title) if title else \
                next(a for a in attacks if 'more damage' in (a.game_text or '').lower()
                     or 'for each' in (a.game_text or '').lower()
                     or 'times the' in (a.game_text or '').lower())
            t, me, opp = self.ready(ref, atk.title)
            neutral(me, hp=300)
            if setup:
                setup(t, me, opp)
            t.heads = True
            await t.attack(me, atk.title)
            got = 400 - t.hp(opp)
            import inspect
            want = expect(atk.damage) if len(inspect.signature(expect).parameters) == 1 \
                else expect(atk.damage, t, me, opp)
            checked += 1
            if got != want:
                bad.append((ref, atk.title, label, got, want))
        print(f'formula cases: {checked} checks, {len(bad)} mismatches')
        for b in bad:
            print('  MISMATCH', b)
        self.assertEqual(bad, [])


if __name__ == '__main__':
    unittest.main()


class EvolvedThisTurn(Base):
    """'If this Pokémon evolved from X during this turn, N more damage.'"""
    async def test_evolved_this_turn_bonus(self):
        import re as _re
        bad = []
        for ref in ('XY3.Accelgor_9', 'SV08.Gholdengo_131', 'SM9.Zebstrika_45', 'SWSH2.Scizor_128',
                    'ME1.Magnezone_47', 'Promo_SWSH.Luxray_23', 'XY11.Persian_89', 'SWSH9.Mothim_11'):
            d = fixtures.definition(ref)
            atk = next(a for a in d.abilities if 'evolved from' in (a.game_text or '').lower())
            m = _re.search(r"evolved from (\w+) during this turn, this attack does (\d+) more", atk.game_text.lower())
            try:
                pre = card(m[1].capitalize())
            except KeyError:
                continue
            t = __import__('tests.bughunt_table', fromlist=['Table']).Table(self)
            low = t.put(pre, P1, 'active')
            t.state.entered_play_turn[low.entity_id] = 0
            for k, v in atk.cost.items():
                t.energy(low, D if k == C else k, v)
            opp = neutral(t.put(self.filler, P2, 'active'), hp=400)
            t.put(self.filler, P2, 'bench')
            evo = t.put(ref, P1, 'hand')
            await t.play(evo, targets=[low.entity_id])
            top = t.active(P1)
            if t.attack_offer(top, atk.title) is None:
                bad.append((ref, 'attack not offered after evolving'))
                continue
            await t.attack(top, atk.title)
            got, want = 400 - t.hp(opp), atk.damage + int(m[2])
            if got != want:
                bad.append((ref, got, want))
        self.assertEqual(bad, [])
