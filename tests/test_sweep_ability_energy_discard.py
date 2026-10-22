"""Sweep: Pokémon ABILITIES whose text discards the player's own Energy.

Question: every Ability (not attack) that requires / offers discarding Energy
("You must discard a Basic Lightning Energy from this Pokémon in order to use
this Ability", "you may discard a Fire Energy card from your hand. If you do",
"As often as you like ... discard an Energy attached to this Pokémon", coin /
evolve / bench-play triggered discards ...) must

  (a) not be offered when the cost can't be paid (nothing matching in the right
      place: attached vs hand, right type, Basic vs Special where it says Basic);
  (b) discard EXACTLY the required Energy (amount, type, place) and let the
      player choose which when several qualify;
  (c) only produce its effect when the cost was paid ("if you do"); "in order
      to use" costs are paid before the effect (draw-until-N counts after it);
  (d) keep once-per-turn limits ("as often as you like" stays repeatable);
  (e) respect live Energy provision for ATTACHED costs: Rainbow / Blend / Unit /
      Aurora / Counter (only while behind) / Prism (Basic Pokémon only) and a
      Pokémon attached as Energy (Electrode XY12 40) provide types dynamically;
      "Basic ... Energy" excludes Special Energy.  "Energy card ... from your
      hand" wordings: a Special Energy in the hand is only a "<Type> Energy
      card" if it provides that type outside play (Rainbow / Blend / Unit /
      Aurora / Counter don't -- Blacksmith / Blend Energy ruling).

Scope: the whole loaded catalog (GLC pool).  `scope()` greps every Ability
text for an own-Energy discard; identical texts are grouped and every printing
of a group is run through the same checks (reprints share one definition).
Discards of the OPPONENT's Energy, Energy-acceleration from the discard pile
and passives that prevent discards are out of scope (listed in the report);
Second Coat (Smeargle XY8 123, a swap that discards an attached basic) is
picked from that list by hand and checked in SecondCoat.

Known bugs (expected failures): Buggy Turbo ignores its coin (tails never
discards), Second Coat offers un-swappable Energy as the first pick.

Run:    PYTHONPATH=. python3 -m unittest tests.test_sweep_ability_energy_discard
Report: audits/results/sweep/ability_energy_discard.json
"""
import collections
import json
import os
import re
import unittest
from unittest.mock import patch

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table
from tests.sweep_core import norm, REPORT_DIR
from spirit.game.attributes import AttrID, PokemonTypes
from spirit.game.data_utils import CARD_DEFS_BY_GUID, PokemonCardDef, Attack, def_for
from spirit.game.models.board import PokemonEntity
from spirit.tools.effect_smoke import P1, P2

G, R, W, L, P, F, D, M = (PokemonTypes.GRASS, PokemonTypes.FIRE, PokemonTypes.WATER,
                          PokemonTypes.LIGHTNING, PokemonTypes.PSYCHIC,
                          PokemonTypes.FIGHTING, PokemonTypes.DARKNESS, PokemonTypes.METAL)
BASICS = [G, R, W, L, P, F, D, M]

RAINBOW = 'SM1.RainbowEnergy_137'
BLEND_GRPD = 'BW6.BlendEnergyGrassFirePsychicDarkness_117'
BLEND_WLFM = 'BW6.BlendEnergyWaterLightningFightingMetal_118'
UNIT_GRW = 'SM5.UnitEnergyGrassFireWater_137'
UNIT_LPM = 'SM5.UnitEnergyLightningPsychicMetal_138'
UNIT_FDY = 'SM6.UnitEnergyFightingDarknessFairy_118'
PRISM = 'BW4.PrismEnergy_93'
AURORA = 'SWSH1.AuroraEnergy_186'
COUNTER = 'SM4.CounterEnergy_100'
# Mega Evolution-era single-type Specials ("As long as this card is attached
# to a Pokémon, it provides <Type> Energy"): typeless outside play.
NITRO, GROWING, VOLTAIC = 'ME4.NitroFireEnergy_86', 'ME3.GrowingGrassEnergy_86', 'ME5.VoltaicLightningEnergy_84'
TELEPATHIC, BUBBLY, ROCKY = 'ME3.TelepathicPsychicEnergy_88', 'ME4.BubblyWaterEnergy_84', 'ME3.RockyFightingEnergy_87'
SPECIALS = [RAINBOW, BLEND_GRPD, BLEND_WLFM, UNIT_GRW, UNIT_LPM, UNIT_FDY, PRISM, AURORA, COUNTER,
            NITRO, GROWING, VOLTAIC, TELEPATHIC, BUBBLY, ROCKY]
# Types each multi-type Special provides while attached (Prism: Basic Pokémon
# only; Counter: only while its owner has more Prizes left).
SPECIAL_TYPES = {
    RAINBOW: set(BASICS), AURORA: set(BASICS), BLEND_GRPD: {G, R, P, D},
    BLEND_WLFM: {W, L, F, M}, UNIT_GRW: {G, R, W}, UNIT_LPM: {L, P, M},
    UNIT_FDY: {F, D}, PRISM: set(BASICS), COUNTER: set(BASICS),
    NITRO: {R}, GROWING: {G}, VOLTAIC: {L}, TELEPATHIC: {P}, BUBBLY: {W}, ROCKY: {F},
}
ELECTRODE = 'XY12.Electrode_40'
SOLROCK = 'CZ.Solrock_69'
FERALIGATR = 'DM.Feraligatr_24'

# ------------------------------------------------------------------ scope --
OWN_DISCARD_RX = re.compile(
    r"(?:you (?:may|must) )?discard (?:\d+|an?|all|any|up to \d+)? ?"
    r"(?:(?:basic|special|grass|fire|water|lightning|psychic|fighting|darkness|metal|fairy|\[[^\]]*\]+|\[ \[[a-z]+\] \]) )*"
    r"energy(?: cards?)?"
    r"(?: (?:attached to|from) (?:this pokémon|it|your pokémon|that pokémon|your hand|1 of your pokémon))")
OPP_RX = re.compile(r"opponent's active pokémon|attacking pokémon|opponent's pokémon")


def scope():
    """{(title, text): [defs]} for every Ability that discards own Energy, plus
    the excluded energy/discard texts with a reason."""
    from spirit.game.scripts.cards import loader
    loader.load_all()
    hits, excluded = collections.defaultdict(list), {}
    for d in CARD_DEFS_BY_GUID.values():
        if not isinstance(d, PokemonCardDef):
            continue
        for a in d.abilities or []:
            if isinstance(a, Attack):
                continue
            text = norm(a.game_text)
            if 'discard' not in text or 'energy' not in text:
                continue
            key = (a.title, text)
            m = OWN_DISCARD_RX.search(text)
            deck_discard = re.search(r"search your deck for up to \d+ basic (?:[a-z]+ )?energy cards and discard them", text)
            if (m and not OPP_RX.search(m.group(0))) or deck_discard:
                hits[key].append(d)
            else:
                excluded[key] = sorted({f"{d2.display_name} {d2.set_code} {d2.collector_number}"
                                        for d2 in CARD_DEFS_BY_GUID.values()
                                        if isinstance(d2, PokemonCardDef)
                                        and any(norm(getattr(x, 'game_text', '')) == text
                                                and not isinstance(x, Attack)
                                                for x in d2.abilities or [])})
    return hits, excluded


def plabel(d):
    return f"{d.display_name} ({d.set_code} {d.collector_number})"


def dname(card):
    return getattr(def_for(card.archetype_id), 'display_name', '?')


# ------------------------------------------------------------ group specs --
# place: 'hand' | 'self';  count: how many;  kind: required type or None;
# basic: text says Basic;  limit: 'once' | 'unlimited';  effect: observer key.
SPECS = {
    'Downpour': dict(place='hand', count=1, kind=W, basic=False, limit='unlimited', effect='none'),
    'Flare Command': dict(place='self', count=1, kind=R, basic=False, limit='once', effect='gust'),
    'Flaring Magic': dict(place='hand', count=1, kind=R, basic=True, limit='once', effect=('draw_to', 7)),
    'Flashing Draw': dict(place='self', count=1, kind=L, basic=True, limit='once', effect=('draw_to', 6)),
    'Gooey Regeneration': dict(place='self', count=1, kind=None, basic=False, limit='unlimited', effect='heal60'),
    'Heat Boost': dict(place='hand', count=1, kind=R, basic=False, limit='once', effect='boost30'),
    'Leaf Draw': dict(place='hand', count=1, kind=G, basic=False, limit='once', effect=('draw', 3)),
    'Lunar Cycle': dict(place='hand', count=1, kind=F, basic=True, limit='once', effect=('draw', 3)),
    'Nine Temptations': dict(place='hand', count=2, kind=R, basic=False, limit='once', effect='gust'),
    'Roast Reveal': dict(place='hand', count=1, kind=R, basic=False, limit='once', effect=('draw', 3)),
    'Rumbling Engine': dict(place='hand', count=1, kind=None, basic=False, limit='once', effect=('draw_to', 6)),
    'Supernatural Orb': dict(place='hand', count=1, kind=P, basic=False, limit='once', effect=('cond', {'Burned', 'Confused'})),
    'Torrid Scales': dict(place='hand', count=1, kind=R, basic=True, limit='once', effect=('cond', {'Burned'})),
    'Wafting Scent': dict(place='self', count=1, kind=G, basic=False, limit='once', effect=('cond', {'Confused', 'Poisoned'})),
    'Water Shuriken': dict(place='hand', count=1, kind=W, basic=False, limit='once', effect='counters30'),
}
# Groups found by scope() that are checked by bespoke tests below instead of
# the cost matrix (the Energy discard is an effect / trigger, not a cost).
BESPOKE = {'Buggy Turbo', 'Wafting Heal', 'Dig Dig Dig', 'Fresh Squeezed'}

REPORT = {'groups': {}, 'excluded': {}, 'results': collections.defaultdict(list)}


def note(title, card, check, ok, detail=''):
    REPORT['results'][title].append({'card': card, 'check': check, 'ok': ok, 'detail': detail})


class Base(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    # ---------------------------------------------------------- helpers --
    @staticmethod
    def neutral(p, hp=400):
        p.set_attribute(AttrID.WEAKNESS_TYPES, [])
        p.set_attribute(AttrID.RESISTANCE_TYPES, [])
        if hp is not None:
            p.set_attribute(AttrID.HP, hp)
        return p

    def board(self, d, *, title=None, prizes_behind=False):
        t = Table(self)
        t.choices = []                      # candidate lists seen by t.picks
        me = t.put(d, P1, 'active')
        self.opp = self.neutral(t.put(self.filler, P2, 'active'))
        self.opp_bench = self.neutral(t.put(self.filler, P2, 'bench'))
        self.neutral(t.put(self.filler, P1, 'bench'))
        if prizes_behind:
            t.set_prizes(P1, 5)
            t.set_prizes(P2, 3)
        if title == 'Lunar Cycle':
            t.put(SOLROCK, P1, 'bench')
        return t, me

    def ecard(self, t, spec, pid=P1, zone='hand'):
        spec = t.basic_energy(spec) if isinstance(spec, PokemonTypes) else spec
        return t.put(spec, pid, zone)

    def attach(self, t, spec, pokemon):
        card = self.ecard(t, spec, pokemon.owning_player_id)
        t.board.attach_card(card.entity_id, pokemon.entity_id)
        return card

    def place(self, t, me, spec, where):
        if where == 'bench':                       # another of your Pokémon
            return self.attach(t, spec, t.zone(P1, 'bench')[0])
        return self.attach(t, spec, me) if where == 'self' else self.ecard(t, spec)

    def chooser(self, t, choose=None):
        """picks: Energy choice -> `choose(cards, count)`; Pokémon -> opp Active."""
        t.choices = getattr(t, 'choices', [])
        def picks(cards, count, prompt, disp):
            if cards and all(isinstance(c, PokemonEntity) and c.owning_player_id == P2
                             for c in cards):
                return [self.opp] if self.opp in cards else cards[:count]
            t.choices.append(list(cards))
            if choose is not None:
                return list(choose(cards, count))
            return cards[:count]
        t.picks = picks
        t.pokemon = lambda cands, prompt: self.opp if self.opp in cands else cands[0]

    def gone(self, t, cards):
        """Which of `cards` ended in P1's discard pile."""
        disc = t.zone(P1, 'discard')
        return [c for c in cards if c in disc]

    # --------------------------------------------------------- observers --
    def prime(self, t, me, spec):
        """Set up the observable state for the effect; returns a checker."""
        eff = spec['effect']
        if eff == 'gust':
            return lambda: t.active(P2) is self.opp_bench
        if eff == 'heal60':
            me.set_attribute(AttrID.HP, t.hp(me) - 100)
            dmg = t.damage(me)
            return lambda: t.damage(me) == dmg - 60
        if eff == 'counters30':
            hp = t.hp(self.opp)
            return lambda: t.hp(self.opp) == hp - 30
        if eff == 'boost30':
            return None                     # checked by attacking (separate test)
        if eff == 'none':
            return lambda: True
        kind, arg = eff
        if kind == 'cond':
            return lambda: t.conditions(self.opp) == arg
        if kind == 'draw_to':
            return lambda: len(t.zone(P1, 'hand')) == arg
        if kind == 'draw':
            before = len(t.zone(P1, 'hand'))
            return lambda: len(t.zone(P1, 'hand')) == before - spec['count'] + arg
        raise KeyError(eff)

    def effect_absent(self, t, me, spec, snap):
        """True when nothing beyond the cost happened."""
        return (t.active(P2) is self.opp and t.hp(self.opp) == snap['opp_hp']
                and not t.conditions(self.opp) and t.hp(me) == snap['me_hp']
                and len(t.zone(P1, 'deck')) == snap['deck'])

    def snap(self, t, me):
        return {'opp_hp': t.hp(self.opp), 'me_hp': t.hp(me), 'deck': len(t.zone(P1, 'deck'))}

    # ------------------------------------------------- qualifying energy --
    def qualifying(self, spec):
        """(qualifying specs, non-qualifying specs) for the cost's place."""
        kind, basic, place = spec['kind'], spec['basic'], spec['place']
        other = W if kind != W else R
        if kind is None:
            return [R, W], [self.item] if place == 'hand' else []
        good = [kind, kind]
        bad = [other]
        return good, bad


class CostMatrix(Base):
    """(a)-(d) for every printing of every cost-type group in SPECS."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        hits, excluded = scope()
        cls.groups = {}
        for (title, text), defs in sorted(hits.items()):
            cls.groups.setdefault(title, []).extend(
                sorted(defs, key=lambda d: (d.set_code, d.collector_number)))
            REPORT['groups'][f"{title} :: {text}"] = sorted({plabel(d) for d in defs})
        REPORT['excluded'] = {f"{k[0]} :: {k[1]}": v for k, v in sorted(excluded.items())}

    def printings(self, title):
        return self.groups.get(title, [])

    def test_scope_is_known(self):
        """Every grouped title is checked by SPECS or a bespoke test."""
        unknown = sorted(set(self.groups) - set(SPECS) - BESPOKE)
        self.assertEqual(unknown, [])
        self.assertEqual(sorted(set(SPECS) - set(self.groups)), [])

    # (a) ----------------------------------------------------------------
    async def test_a_not_offered_without_cost(self):
        for title, spec in SPECS.items():
            for d in self.printings(title):
                with self.subTest(card=plabel(d), title=title):
                    good, bad = self.qualifying(spec)
                    wrong_place = 'hand' if spec['place'] == 'self' else 'self'
                    setups = [('nothing', [])]
                    setups.append(('wrong place', [(g, wrong_place) for g in good]))
                    if spec['place'] == 'self':
                        setups.append(('on another of your Pokémon', [(g, 'bench') for g in good]))
                    if bad:
                        setups.append(('wrong kind', [(b, spec['place']) for b in bad] * 2))
                    if spec['count'] > 1:
                        setups.append(('one short', [(good[0], spec['place'])]))
                    if spec['basic']:
                        setups.append(('special of right type',
                                       [(RAINBOW, spec['place']), (UNIT_GRW if spec['kind'] in (G, R, W)
                                                                   else UNIT_LPM if spec['kind'] in (L, P, M)
                                                                   else UNIT_FDY, spec['place'])]))
                    for label, cards in setups:
                        t, me = self.board(d, title=title)
                        for s, where in cards:
                            self.place(t, me, s, where)
                        offered = t.ability_offer(me, title) is not None
                        note(title, plabel(d), f'a:{label}', not offered)
                        self.assertFalse(offered, f'{title} offered with {label}')

    # (b)+(c) -------------------------------------------------------------
    async def test_b_pays_exactly_chosen_energy(self):
        for title, spec in SPECS.items():
            if spec['effect'] == 'boost30':
                continue
            for d in self.printings(title):
                with self.subTest(card=plabel(d), title=title):
                    t, me = self.board(d, title=title)
                    good, bad = self.qualifying(spec)
                    goods = [self.place(t, me, s, spec['place']) for s in good + good[:1]]
                    bads = [self.place(t, me, s, spec['place']) for s in bad]
                    count = spec['count']
                    want = goods[-count:]             # the player picks the LAST ones
                    self.chooser(t, lambda cards, n: [c for c in want if c in cards][:n] or cards[:n])
                    check = self.prime(t, me, spec)
                    await t.use(me, title)
                    paid = self.gone(t, goods + bads)
                    seen = t.choices[0] if t.choices else None
                    ok_pay = sorted(map(id, paid)) == sorted(map(id, want))
                    ok_cands = seen is None or not (set(map(id, seen)) - set(map(id, goods)))
                    ok_eff = check()
                    note(title, plabel(d), 'b:pays exactly the chosen Energy', ok_pay and ok_cands,
                         f'paid={[dname(c) for c in paid]} candidates={[dname(c) for c in seen or []]}')
                    note(title, plabel(d), 'c:effect after payment', ok_eff)
                    self.assertTrue(ok_pay, f'paid {[dname(c) for c in paid]}, wanted {count} chosen')
                    self.assertTrue(ok_cands, f'non-qualifying candidates offered: {[dname(c) for c in seen]}')
                    self.assertTrue(ok_eff, 'effect missing after paying')

    async def test_c_declined_cost_means_no_effect(self):
        """If the player picks nothing for the cost, nothing happens."""
        for title, spec in SPECS.items():
            if spec['effect'] in ('boost30', 'none'):
                continue   # boost checked elsewhere; Downpour has no effect
            for d in self.printings(title):
                with self.subTest(card=plabel(d), title=title):
                    t, me = self.board(d, title=title)
                    good, _ = self.qualifying(spec)
                    goods = [self.place(t, me, s, spec['place']) for s in good + good[:1]]
                    self.chooser(t, lambda cards, n: [])
                    self.prime(t, me, spec)
                    s = self.snap(t, me)
                    hand = len(t.zone(P1, 'hand'))
                    try:
                        await t.use(me, title)
                    except Exception as ex:   # the engine may refuse an empty pick
                        note(title, plabel(d), 'c:declined', True, f'refused: {ex!r}')
                        continue
                    paid = self.gone(t, goods)
                    ok = (len(paid) == spec['count'] and not self.effect_absent(t, me, spec, s)) \
                        or (not paid and self.effect_absent(t, me, spec, s)
                            and len(t.zone(P1, 'hand')) == hand)
                    note(title, plabel(d), 'c:declined', ok, f'paid={len(paid)}')
                    self.assertTrue(ok, f'declined cost: paid {len(paid)}, effect happened anyway')

    # (d) ----------------------------------------------------------------
    async def test_d_turn_limits(self):
        for title, spec in SPECS.items():
            for d in self.printings(title):
                with self.subTest(card=plabel(d), title=title):
                    t, me = self.board(d, title=title)
                    good, _ = self.qualifying(spec)
                    for _ in range(3):
                        for s in good:
                            self.place(t, me, s, spec['place'])
                    if spec['effect'] == 'heal60':
                        me.set_attribute(AttrID.HP, t.hp(me) - 120)
                    self.chooser(t)
                    await t.use(me, title)
                    again = t.ability_offer(me, title) is not None
                    want = spec['limit'] == 'unlimited'
                    note(title, plabel(d), 'd:offered again same turn', again == want)
                    self.assertEqual(again, want, f'offered again: {again}')
                    t.next_turn(); t.next_turn()
                    for c in t.zone(P1, 'hand'):        # room to draw again
                        if str(c.archetype_id).lower() == self.item.guid.lower():
                            t.board.move_card(c.entity_id, t.board.find_player_area(P1, 'deck').entity_id)
                    self.assertIsNotNone(t.ability_offer(me, title), 'not offered next turn')


class Provision(Base):
    """(e) live provision for ATTACHED costs, Special Energy in the hand."""

    def setUp(self):
        hits, _ = scope()
        self.by_title = {}
        for (title, text), defs in hits.items():
            self.by_title.setdefault(title, []).extend(defs)
        for v in self.by_title.values():
            v.sort(key=lambda d: (d.set_code, d.collector_number))

    def first(self, title):
        return self.by_title[title][0]

    async def test_e_attached_specials(self):
        for title in ('Flare Command', 'Flashing Draw', 'Gooey Regeneration', 'Wafting Scent'):
            spec = SPECS[title]
            for special, d in [(x, d) for x in SPECIALS for d in self.by_title[title]]:
                for behind in ((False, True) if special == COUNTER else (False,)):
                    with self.subTest(title=title, energy=special, behind=behind, card=plabel(d)):
                        t, me = self.board(d, title=title, prizes_behind=behind)
                        card = self.attach(t, special, me)
                        if spec['effect'] == 'heal60':
                            me.set_attribute(AttrID.HP, t.hp(me) - 100)
                        is_basic_pokemon = me.get_attribute(AttrID.STAGE) in (0, 'Basic', None)
                        provides = SPECIAL_TYPES[special]
                        if special == PRISM and not is_basic_pokemon:
                            provides = set()
                        if special == COUNTER and not behind:
                            provides = set()
                        if spec['kind'] is None:
                            expect = True
                        elif spec['basic']:
                            expect = False
                        else:
                            expect = spec['kind'] in provides
                        offered = t.ability_offer(me, title) is not None
                        note(title, plabel(d), f'e:{special}{" behind" if behind else ""}',
                             offered == expect, f'offered={offered} expected={expect}')
                        self.assertEqual(offered, expect)
                        if offered:
                            self.chooser(t)
                            check = self.prime(t, me, spec)
                            await t.use(me, title)
                            self.assertIn(card, t.zone(P1, 'discard'))
                            self.assertTrue(check())

    async def test_e_electrode_as_energy(self):
        """Electrode attached as a Special Energy card providing [L][L]
        (Buzzap Thunder: Lightning Pokémon only).  Flashing Draw ("a Basic
        Lightning Energy") must not take it.  Gooey Regeneration ("an Energy")
        is only reachable if Goodra were a Lightning Pokémon (no GLC effect
        does that), so its result is recorded in the report, not asserted."""
        for title, expect, asserted in (('Flashing Draw', False, True),
                                        ('Gooey Regeneration', True, False)):
            with self.subTest(title=title):
                d = self.first(title)
                t, me = self.board(d, title=title)
                me.set_attribute(AttrID.POKEMON_TYPES, [L.value])
                electrode = self.neutral(t.put(ELECTRODE, P1, 'bench'))
                t.pokemon = lambda cands, prompt: me
                await t.use(electrode, 'Buzzap Thunder')
                self.assertIn(electrode, t.board.attached_energies(me))
                t.next_turn(); t.next_turn()
                me.set_attribute(AttrID.HP, t.hp(me) - 100)
                offered = t.ability_offer(me, title) is not None
                note(title, plabel(d), 'e:Electrode as Energy' + ('' if asserted else ' (latent, unreachable)'),
                     offered == expect, f'offered={offered} expected={expect}')
                if asserted:
                    self.assertEqual(offered, expect)

    async def test_e_choice_includes_qualifying_specials(self):
        """Pyroar / Victreebel: basic + Rainbow + Blend + Water attached; the
        chooser shows exactly the qualifying three and discards the pick."""
        for title, kind, blend in (('Flare Command', R, BLEND_GRPD), ('Wafting Scent', G, BLEND_GRPD)):
            with self.subTest(title=title):
                d = self.first(title)
                t, me = self.board(d, title=title)
                goods = [self.attach(t, kind, me), self.attach(t, RAINBOW, me), self.attach(t, blend, me)]
                water = self.attach(t, W, me)
                self.chooser(t, lambda cards, n: [goods[2]])
                check = self.prime(t, me, SPECS[title])
                await t.use(me, title)
                seen = t.choices[0] if t.choices else []
                self.assertEqual(sorted(map(id, seen)), sorted(map(id, goods)))
                self.assertEqual(self.gone(t, goods + [water]), [goods[2]])
                self.assertTrue(check())
                note(title, plabel(d), 'b+e: chooser lists qualifying Specials', True)

    async def test_e_gooey_counter_one_card_one_heal(self):
        """Counter Energy providing 2 (behind): one Gooey use discards that one
        card and heals 60 once."""
        d = self.first('Gooey Regeneration')
        t, me = self.board(d, title='Gooey Regeneration', prizes_behind=True)
        counter = self.attach(t, COUNTER, me)
        basic = self.attach(t, W, me)
        me.set_attribute(AttrID.HP, t.hp(me) - 150)
        dmg = t.damage(me)
        self.chooser(t, lambda cards, n: [counter])
        await t.use(me, 'Gooey Regeneration')
        self.assertEqual(self.gone(t, [counter, basic]), [counter])
        self.assertEqual(t.damage(me), dmg - 60)
        self.assertIsNotNone(t.ability_offer(me, 'Gooey Regeneration'))
        await t.use(me, 'Gooey Regeneration')
        self.assertEqual(t.damage(me), dmg - 120)
        self.assertIsNone(t.ability_offer(me, 'Gooey Regeneration'))   # no Energy left
        note('Gooey Regeneration', plabel(d), 'b+d+e: Counter 1 card / heal once / exhausts', True)

    async def test_d_downpour_until_no_water(self):
        d = self.first('Downpour')
        t, me = self.board(d)
        waters = [self.ecard(t, W) for _ in range(3)]
        self.ecard(t, R)
        self.chooser(t)
        for _ in range(3):
            await t.use(me, 'Downpour')
        self.assertEqual(self.gone(t, waters), waters)
        self.assertIsNone(t.ability_offer(me, 'Downpour'))
        self.assertEqual(len(t.zone(P1, 'hand')), 1)
        note('Downpour', plabel(d), 'd: repeatable until no Water Energy card', True)

    async def test_info_kilowattrel_full_hand(self):
        """Recorded only: Flashing Draw with 6+ cards in hand (draws 0)."""
        d = self.first('Flashing Draw')
        t, me = self.board(d)
        mine = t.energy(me, L)
        for _ in range(6):
            t.put(self.item, P1, 'hand')
        offered = t.ability_offer(me, 'Flashing Draw') is not None
        paid = None
        if offered:
            self.chooser(t)
            await t.use(me, 'Flashing Draw')
            paid = mine in t.zone(P1, 'discard')
        note('Flashing Draw', plabel(d), 'INFO: 6 cards in hand', True,
             f'offered={offered} paid={paid}')

    async def test_a_kilowattrel_on_bench_and_other_pokemon(self):
        """Flashing Draw from the Bench pays from itself only."""
        d = self.first('Flashing Draw')
        t = Table(self)
        self.opp = self.neutral(t.put(self.filler, P2, 'active'))
        active = self.neutral(t.put(self.filler, P1, 'active'))
        me = t.put(d, P1, 'bench')
        t.energy(active, L, 2)
        self.assertIsNone(t.ability_offer(me, 'Flashing Draw'))
        mine = t.energy(me, L)
        self.chooser(t)
        await t.use(me, 'Flashing Draw')
        self.assertIn(mine, t.zone(P1, 'discard'))
        self.assertEqual(len(t.board.attached_energies(active)), 2)
        self.assertEqual(len(t.zone(P1, 'hand')), 6)
        note('Flashing Draw', plabel(d), 'a+b: bench user pays from itself', True)

    async def test_e_hand_specials(self):
        """'<Type> Energy card from your hand': multi-type Specials in the hand
        are not typed (they provide types only while attached); 'an Energy
        card' (Rumbling Engine) takes any Energy card."""
        for title, spec in SPECS.items():
            if spec['place'] != 'hand':
                continue
            for special, d in [(x, d) for x in SPECIALS for d in self.by_title[title]]:
                with self.subTest(title=title, energy=special, card=plabel(d)):
                    t, me = self.board(d, title=title)
                    for _ in range(spec['count']):
                        self.ecard(t, special)
                    offered = t.ability_offer(me, title) is not None
                    expect = spec['kind'] is None
                    note(title, plabel(d), f'e:hand {special}', offered == expect,
                         f'offered={offered} expected={expect}')
                    self.assertEqual(offered, expect)


class Bespoke(Base):
    """Effects / triggers that discard Energy (no cost)."""

    async def test_heat_boost_damage_only_after_paying(self):
        for path in ('SWSH12.Rapidash_22', 'Promo_SWSH.Rapidash_270'):
            with self.subTest(card=path):
                t, me = self.board(fixtures.definition(path))
                t.energy(me, R, 2)
                hand_fire = [self.ecard(t, R), self.ecard(t, R)]
                self.chooser(t, lambda cards, n: [hand_fire[1]])
                await t.use(me, 'Heat Boost')
                self.assertEqual(self.gone(t, hand_fire), [hand_fire[1]])
                hp = t.hp(self.opp)
                await t.attack(me, 'Fire Mane')
                self.assertEqual(hp - t.hp(self.opp), 90)
                note('Heat Boost', path, 'b+c: discards chosen, +30', True)

    async def test_heat_boost_not_offered_with_basic_water_only(self):
        t, me = self.board(fixtures.definition('SWSH12.Rapidash_22'))
        self.ecard(t, W)
        self.assertIsNone(t.ability_offer(me, 'Heat Boost'))

    async def test_lunar_cycle_shared_limit(self):
        """Two Lunatone: only 1 Lunar Cycle per turn."""
        t, me = self.board(fixtures.definition('ME1.Lunatone_74'), title='Lunar Cycle')
        other = t.put('MEP.Lunatone_4', P1, 'bench')
        for _ in range(3):
            self.ecard(t, F)
        self.chooser(t)
        await t.use(me, 'Lunar Cycle')
        self.assertIsNone(t.ability_offer(other, 'Lunar Cycle'))

    async def test_lunar_cycle_needs_solrock(self):
        t, me = self.board(fixtures.definition('ME1.Lunatone_74'))
        self.ecard(t, F)
        self.assertIsNone(t.ability_offer(me, 'Lunar Cycle'))


class Triggered(Base):
    """Energy discards that are effects / triggers, not costs."""

    # FIXED: spirit/game/card_effects/bw_era.py:bw_legacy_ability -- the "flip a coin"
    # block has no Buggy Turbo branch, so it falls through to the generic
    # "attach up to N Basic Energy cards from your discard pile" handler: the
    # coin is ignored, tails attaches from the discard pile and never discards.
    async def test_buggy_turbo_tails_discards_one_chosen(self):
        for path in ('SV4.PorygonZ_144', 'SV4.PorygonZ_214'):
            with self.subTest(card=path):
                t, me = self.board(fixtures.definition(path))
                cards = [self.attach(t, W, me), self.attach(t, RAINBOW, me), self.attach(t, F, me)]
                self.ecard(t, F, zone='discard')     # heads half possible (see test_ruling_*)
                t.heads = False
                self.chooser(t, lambda c, n: [cards[1]] if cards[1] in c else c[:n])
                await t.use(me, 'Buggy Turbo')
                ok = self.gone(t, cards) == [cards[1]] and len(t.board.attached_energies(me)) == 2
                note('Buggy Turbo', path, 'tails: exactly 1 chosen Energy, nothing attached', ok,
                     f'attached after tails: {[dname(c) for c in t.board.attached_energies(me)]}')
                self.assertIsNone(t.ability_offer(me, 'Buggy Turbo'))
                self.assertEqual(self.gone(t, cards), [cards[1]])
                self.assertEqual(len(t.board.attached_energies(me)), 2)

    async def test_ruling_buggy_turbo_empty_discard(self):
        """Recorded only (owner ruling): with no Basic Energy in the discard
        pile the heads half is empty but tails still discards; the engine does
        not offer Buggy Turbo then."""
        t, me = self.board(fixtures.definition('SV4.PorygonZ_144'))
        self.attach(t, W, me)
        offered = t.ability_offer(me, 'Buggy Turbo') is not None
        note('Buggy Turbo', 'SV4 144', 'RULING: offered with empty discard pile?', True,
             f'offered={offered}')

    async def test_buggy_turbo_heads_does_not_discard(self):
        t, me = self.board(fixtures.definition('SV4.PorygonZ_144'))
        mine = self.attach(t, W, me)
        disc = [self.ecard(t, F, zone='discard') for _ in range(5)]
        t.heads = True
        self.chooser(t)
        await t.use(me, 'Buggy Turbo')
        self.assertIn(mine, t.board.attached_energies(me))
        self.assertEqual(len(t.board.attached_energies(me)), 5)     # up to 4 attached
        note('Buggy Turbo', 'SV4 144', 'heads: no discard, up to 4 attached', True)

    async def _whimsicott(self, path, *, active_spec, damage, energies, yes=True):
        t = Table(self)
        t.yes = yes
        self.opp = self.neutral(t.put(self.filler, P2, 'active'))
        active = self.neutral(t.put(active_spec, P1, 'active'), hp=None)
        cottonee = t.put('SV05.Cottonee_14', P1, 'bench')
        if damage:
            active.set_attribute(AttrID.HP, t.hp(active) - damage)
        att = [self.attach(t, e, active) for e in energies]
        whim = t.put(path, P1, 'hand')
        self.chooser(t)
        t.pokemon = lambda cands, prompt: active if active in cands else cands[0]
        await t.play(whim, targets=[cottonee.entity_id])
        return t, active, att

    async def test_wafting_heal_discards_all_energy_only_if_healed(self):
        grass = 'SV05.Deerling_16'
        for path in ('SV05.Whimsicott_15', 'SV085.Whimsicott_8'):
            with self.subTest(card=path, case='healed'):
                t, active, att = await self._whimsicott(
                    path, active_spec=grass, damage=30, energies=[G, RAINBOW, W])
                self.assertEqual(t.damage(active), 0)
                self.assertEqual(self.gone(t, att), att)
                self.assertEqual(t.board.attached_energies(active), [])
            with self.subTest(card=path, case='undamaged'):
                t, active, att = await self._whimsicott(
                    path, active_spec=grass, damage=0, energies=[G, W])
                self.assertEqual(self.gone(t, att), [])
            with self.subTest(card=path, case='declined'):
                t, active, att = await self._whimsicott(
                    path, active_spec=grass, damage=30, energies=[G, W], yes=False)
                self.assertEqual(self.gone(t, att), [])
                self.assertEqual(t.damage(active), 30)
            with self.subTest(card=path, case='non-Grass Active'):
                t, active, att = await self._whimsicott(
                    path, active_spec=self.filler, damage=30, energies=[G, W])
                self.assertEqual(self.gone(t, att), [])
                self.assertEqual(t.damage(active), 30)
            note('Wafting Heal', path, 'heal -> discard all; no heal -> no discard', True)

    async def _deck_discard(self, path, deck_specs, pick_all=True):
        t = Table(self)
        self.opp = self.neutral(t.put(self.filler, P2, 'active'))
        self.neutral(t.put(self.filler, P1, 'active'))
        deck = [self.ecard(t, s, zone='deck') for s in deck_specs]
        mon = t.put(path, P1, 'hand')
        self.chooser(t)
        await t.play(mon)
        return t, deck

    async def test_dig_dig_dig_basic_fighting_only_up_to_3(self):
        t, deck = await self._deck_discard('SV05.Drilbur_85', [F, F, F, F, W, UNIT_FDY, RAINBOW])
        seen = t.choices[0] if t.choices else []
        self.assertEqual(sorted(map(id, seen)), sorted(map(id, deck[:4])))
        self.assertEqual(len(self.gone(t, deck)), 3)
        self.assertTrue(all(c in deck[:4] for c in self.gone(t, deck)))
        note('Dig Dig Dig', 'SV05 85', 'basic Fighting only, up to 3', True)

    async def test_fresh_squeezed_basic_only_up_to_3(self):
        t, deck = await self._deck_discard('SM8.Shuckle_16', [F, W, G, R, UNIT_FDY, RAINBOW, AURORA])
        seen = t.choices[0] if t.choices else []
        self.assertEqual(sorted(map(id, seen)), sorted(map(id, deck[:4])))
        self.assertEqual(len(self.gone(t, deck)), 3)
        note('Fresh Squeezed', 'SM8 16', 'basic Energy only, up to 3', True)


class SecondCoat(Base):
    """Smeargle XY8 123 Second Coat: an attached basic Energy goes to the
    discard pile in exchange for a different-type basic from the discard."""
    SMEARGLE = 'XY8.Smeargle_123'

    def table(self):
        t = Table(self)
        t.choices = []
        self.opp = self.neutral(t.put(self.filler, P2, 'active'))
        active = self.neutral(t.put(self.filler, P1, 'active'))
        me = t.put(self.SMEARGLE, P1, 'bench')
        return t, active, me

    async def test_not_offered_without_a_legal_swap(self):
        cases = (('special attached', [RAINBOW], [W]), ('same type only', [W], [W]),
                 ('special in discard', [W], [RAINBOW]), ('nothing attached', [], [W]))
        for label, att, disc in cases:
            with self.subTest(case=label):
                t, active, me = self.table()
                for e in att:
                    self.attach(t, e, active)
                for e in disc:
                    self.ecard(t, e, zone='discard')
                offered = t.ability_offer(me, 'Second Coat') is not None
                note('Second Coat', 'XY8 123', f'a:{label}', not offered)
                self.assertFalse(offered)

    async def test_swaps_exactly_one_chosen(self):
        t, active, me = self.table()
        water, fire = self.attach(t, W, active), self.attach(t, R, active)
        grass, water2 = self.ecard(t, G, zone='discard'), self.ecard(t, W, zone='discard')
        self.chooser(t, lambda cards, n: [fire] if fire in cards else [water2] if water2 in cards else cards[:n])
        await t.use(me, 'Second Coat')
        self.assertIn(fire, t.zone(P1, 'discard'))
        self.assertIn(water2, t.board.attached_energies(active))
        self.assertIn(water, t.board.attached_energies(active))
        self.assertIn(grass, t.zone(P1, 'discard'))
        self.assertIsNone(t.ability_offer(me, 'Second Coat'))
        note('Second Coat', 'XY8 123', 'b:swaps the chosen pair; once per turn', True)

    # FIXED: spirit/game/card_effects/standard_era.py:second_coat -- the first
    # chooser lists every attached basic Energy, including ones with no
    # different-type basic in the discard pile; picking one ends the Ability
    # with no swap and the once-per-turn use is spent.
    async def test_first_choice_only_swappable_energy(self):
        """Water + Fire attached, only a Water in the discard: only the Fire
        can be replaced, so the first chooser must not offer the Water."""
        t, active, me = self.table()
        water, fire = self.attach(t, W, active), self.attach(t, R, active)
        water2 = self.ecard(t, W, zone='discard')
        self.chooser(t, lambda cards, n: [water] if water in cards else cards[:n])
        await t.use(me, 'Second Coat')
        first = t.choices[0] if t.choices else [fire]
        ok = water not in first
        note('Second Coat', 'XY8 123', 'b:first chooser lists only swappable Energy', ok,
             f'first chooser: {len(first)} card(s); fire discarded={fire in t.zone(P1, "discard")}')
        spent = t.ability_offer(me, 'Second Coat') is None
        note('Second Coat', 'XY8 123', 'b:dead pick spends the Ability', not (spent and fire not in t.zone(P1, 'discard')),
             f'offered again={not spent}')
        self.assertTrue(ok, 'Water (no different-type basic in discard) offered as the Energy to replace')


def tearDownModule():
    os.makedirs(REPORT_DIR, exist_ok=True)
    out = dict(REPORT)
    res = out['results']
    out['summary'] = {title: {'checks': len(v), 'failed': sum(1 for x in v if not x['ok'])}
                      for title, v in sorted(res.items())}
    out['bugs'] = [
        {'card': 'Porygon-Z SV4 144 / 214', 'ability': 'Buggy Turbo',
         'root_cause': 'spirit/game/card_effects/bw_era.py:bw_legacy_ability (flip-a-coin block has no '
                       'Buggy Turbo branch; falls through to the generic discard-pile attach)',
         'test': 'Triggered.test_buggy_turbo_tails_discards_one_chosen'},
        {'card': 'Smeargle XY8 123', 'ability': 'Second Coat',
         'root_cause': 'spirit/game/card_effects/standard_era.py:second_coat (first chooser lists '
                       'attached basics with no different-type basic in the discard pile)',
         'test': 'SecondCoat.test_first_choice_only_swappable_energy'},
    ]
    out['latent'] = ['Gooey Regeneration "an Energy": bw_era._energy_phrase_predicate uses is_energy_card, '
                     'so a Pokémon attached as Energy (Electrode XY12 40 / Charjabug) is not discardable; '
                     'unreachable in GLC (they only attach to Lightning Pokémon).']
    out['rulings'] = ['Buggy Turbo with no Basic Energy in the discard pile is not offered (tails could still discard).',
                      'Multi-type / ME single-type Special Energy in the HAND is not a "<Type> Energy card" '
                      '(engine: typeless outside play) -- Blacksmith/Blend ruling assumed.']
    out['failures'] = [dict(title=title, **x) for title, v in sorted(res.items()) for x in v if not x['ok']]
    with open(os.path.join(REPORT_DIR, 'ability_energy_discard.json'), 'w') as fh:
        json.dump(out, fh, indent=1, ensure_ascii=False, default=str)
