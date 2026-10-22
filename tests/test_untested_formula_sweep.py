"""Bug hunt (Oct 14) part 2: damage formulas of never-tested cards.

The 1,411 untested Pokemon that are not in live decks (see HANDOFF section
22) were run through the no-op detector, which cannot judge damage AMOUNTS.
This sweep checks the commonest formula wordings across all of them on a
neutral board (no Weakness/Resistance, opponent at 400 HP).
"""
import json
import re
import unittest
from unittest.mock import patch

from tests import test_hgss_rules as fixtures
from tests.test_untested_live_cards import Base, neutral, D, R, W, P1, P2
from spirit.game.attributes import AttrID, PokemonTypes, TrainerType
from spirit.game.session.passives import energy_provided_options
from spirit.game.session.effects import EffectContext

import os
TOOL = 'SV065.Powerglass_63'
REFS = os.path.join(os.path.dirname(__file__), '..', 'dev_notes', 'untested_pokemon_oct14.txt')


def _attacks():
    try:
        refs = open(REFS).read().split()
    except OSError:
        return []
    out = []
    for ref in refs:
        try:
            d = fixtures.definition(ref)
        except Exception:
            continue
        has_ability = any(type(a).__name__ != 'Attack' for a in d.abilities)
        for a in d.abilities:
            if type(a).__name__ == 'Attack':
                text = ' '.join((a.game_text or '').lower().replace('’', "'").split())
                out.append((ref, a, text, has_ability))
    return out


class FormulaSweep(Base):
    async def run_case(self, ref, title, heads, setup=None):
        t, me, opp = self.ready(ref, title)
        neutral(me, hp=300)
        if setup:
            setup(t, me, opp)
        flips = iter(heads) if isinstance(heads, list) else None
        t.heads = (lambda _title: next(flips)) if flips else heads
        with patch.object(EffectContext, 'flip_until_tails',
                          lambda ctx, title='': _const(heads if isinstance(heads, int) else 0)):
            await t.attack(me, title)
        return 400 - t.hp(opp)

    async def test_sweep(self):
        cases = _attacks()
        if not cases:
            self.skipTest('reference list not available')
        bad, checked = [], 0
        for ref, a, text, has_ability in cases:
            if has_ability:
                continue           # passives can change damage
            base = a.damage
            m = re.fullmatch(r"flip a coin\. if heads, this attack does (\d+) more damage\.", text)
            if m:
                for heads, want in ((True, base + int(m[1])), (False, base)):
                    got = await self.run_case(ref, a.title, heads)
                    checked += 1
                    if got != want:
                        bad.append((ref, a.title, heads, got, want))
                continue
            m = re.fullmatch(r"flip (\d+) coins\. this attack does (\d+) (?:damage times the number of heads|damage for each heads)\.", text)
            if m:
                n, per = int(m[1]), int(m[2])
                seq = [True] * (n - 1) + [False]
                got = await self.run_case(ref, a.title, seq)
                checked += 1
                if got != per * (n - 1):
                    bad.append((ref, a.title, 'n-1 heads', got, per * (n - 1)))
                continue
            m = re.fullmatch(r"flip (\d+) coins\. this attack does (\d+) more damage for each heads\.", text)
            if m:
                n, per = int(m[1]), int(m[2])
                got = await self.run_case(ref, a.title, [True] * n)
                checked += 1
                if got != base + per * n:
                    bad.append((ref, a.title, 'all heads', got, base + per * n))
                continue
            m = re.fullmatch(r"this attack does (\d+) (more|less) damage for each colorless in your opponent's active pokémon's retreat cost\.", text)
            if m:
                per = int(m[1]) * (1 if m[2] == 'more' else -1)

                def setup(t, me, opp):
                    opp.set_attribute(AttrID.RETREAT_COST, 2)
                got = await self.run_case(ref, a.title, True, setup)
                checked += 1
                if got != max(0, base + 2 * per):
                    bad.append((ref, a.title, 'retreat 2', got, max(0, base + 2 * per)))
                continue
            m = re.fullmatch(r"this attack does (\d+) damage for each colorless in your opponent's active pokémon's retreat cost\.", text)
            if m:
                def setup(t, me, opp):
                    opp.set_attribute(AttrID.RETREAT_COST, 3)
                got = await self.run_case(ref, a.title, True, setup)
                checked += 1
                if got != 3 * int(m[1]):
                    bad.append((ref, a.title, 'retreat 3', got, 3 * int(m[1])))
                continue
            m = re.fullmatch(r"flip a coin until you get tails\. this attack does (\d+) (more )?damage for each heads\.", text)
            if m:
                want = (base if m[2] else 0) + 2 * int(m[1])
                got = await self.run_case(ref, a.title, 2)
                checked += 1
                if got != want:
                    bad.append((ref, a.title, '2 heads', got, want))
            m = re.fullmatch(r"if your opponent's active pokémon is an? (grass|fire|water|lightning|psychic|fighting|darkness|metal|fairy|dragon|colorless) pokémon, this attack does (\d+) more damage\.", text)
            if m:
                kind = getattr(PokemonTypes, m[1].upper())
                for match in (False, True):
                    def setup(t, me, opp, match=match):
                        opp.set_attribute(AttrID.POKEMON_TYPES,
                                          [kind.value] if match else [PokemonTypes.COLORLESS.value if kind != PokemonTypes.COLORLESS else PokemonTypes.FIRE.value])
                    got = await self.run_case(ref, a.title, True, setup)
                    checked += 1
                    want = base + (int(m[2]) if match else 0)
                    if got != want:
                        bad.append((ref, a.title, f'type match={match}', got, want))
                continue
            m = re.fullmatch(r"if this pokémon has any (grass|fire|water|lightning|psychic|fighting|darkness|metal|fairy) energy attached(?: to it)?, this attack does (\d+) more damage\.", text)
            if m:
                kind = getattr(PokemonTypes, m[1].upper())
                for extra in (False, True):
                    t, me, opp = self.ready(ref, a.title)
                    neutral(me, hp=300)
                    already = any(kind.value in o for c in me.children
                                  for o in energy_provided_options(t.board, c))
                    if already and not extra:
                        continue
                    if extra and not already:
                        t.energy(me, kind, 1)
                    t.heads = True
                    await t.attack(me, a.title)
                    got = 400 - t.hp(opp)
                    checked += 1
                    want = base + (int(m[2]) if extra else 0)
                    if got != want:
                        bad.append((ref, a.title, f'{m[1]} energy={extra}', got, want))
                continue
            m = re.fullmatch(r"you may do (\d+) more damage\. if you do, this pokémon does (\d+) damage to itself\.", text)
            if m:
                for yes in (False, True):
                    t, me, opp = self.ready(ref, a.title)
                    neutral(me, hp=300)
                    t.yes = yes
                    await t.attack(me, a.title)
                    checked += 1
                    got = (400 - t.hp(opp), 300 - t.hp(me))
                    want = (base + (int(m[1]) if yes else 0), int(m[2]) if yes else 0)
                    if got != want:
                        bad.append((ref, a.title, f'yes={yes}', got, want))
                continue
            m = re.fullmatch(r"(?:this attack )?does (\d+) (more |less )?damage for each energy attached to your opponent's active pokémon\.", text)
            if m:
                def setup(t, me, opp):
                    t.energy(opp, D, 2)
                got = await self.run_case(ref, a.title, True, setup)
                checked += 1
                per = int(m[1])
                want = base + 2 * per if m[2] == 'more ' else (
                    max(0, base - 2 * per) if m[2] == 'less ' else 2 * per)
                if got != want:
                    bad.append((ref, a.title, '2 energy', got, want))
                continue
            m = re.fullmatch(r"if (this pokémon|your opponent's active pokémon) has a pokémon tool(?: card)? attached(?: to it)?, this attack does (\d+) more damage\.", text)
            if m:
                for tool in (False, True):
                    def setup(t, me, opp, tool=tool, mine=m[1] == 'this pokémon'):
                        if tool:
                            card = t.put(TOOL, P1 if mine else P2, 'hand')
                            t.board.attach_card(card.entity_id, (me if mine else opp).entity_id)
                    got = await self.run_case(ref, a.title, True, setup)
                    checked += 1
                    want = base + (int(m[2]) if tool else 0)
                    if got != want:
                        bad.append((ref, a.title, f'{m[1]} tool={tool}', got, want))
                continue
            m = re.fullmatch(r"if your opponent's active pokémon is (a basic|an evolution|a stage 1|a stage 2) pokémon, this attack does (\d+) more damage\.", text)
            if m:
                for spec, stage in (('SM12.Piplup_54', 'basic'), ('SM12.Prinplup_55', 'stage 1'),
                                    ('SM12.Empoleon_56', 'stage 2')):
                    def setup(t, me, opp, spec=spec):
                        t.board.find_player_area(P2, 'activePokemonArea').remove_child(opp)
                        new = neutral(t.put(spec, P2, 'active'), hp=400)
                        t.new_opp = new
                    t, me, opp = self.ready(ref, a.title)
                    neutral(me, hp=300)
                    setup(t, me, opp)
                    t.heads = True
                    await t.attack(me, a.title)
                    got = 400 - t.hp(t.new_opp)
                    checked += 1
                    hit = {'a basic': stage == 'basic', 'an evolution': stage != 'basic',
                           'a stage 1': stage == 'stage 1', 'a stage 2': stage == 'stage 2'}[m[1]]
                    want = base + (int(m[2]) if hit else 0)
                    if got != want:
                        bad.append((ref, a.title, f'opp {stage}', got, want))
                continue
            m = re.fullmatch(r"this attack does (\d+) damage for each pokémon tool attached to all of your pokémon\.", text)
            if m:
                def setup(t, me, opp):
                    for holder in (me, t.put(self.filler, P1, 'bench')):
                        card = t.put(TOOL, P1, 'hand')
                        t.board.attach_card(card.entity_id, holder.entity_id)
                    card = t.put(TOOL, P2, 'hand')
                    t.board.attach_card(card.entity_id, opp.entity_id)     # not counted
                got = await self.run_case(ref, a.title, True, setup)
                checked += 1
                if got != 2 * int(m[1]):
                    bad.append((ref, a.title, '2 own tools', got, 2 * int(m[1])))
                continue
            m = re.fullmatch(r"if any of your pokémon were knocked out by damage from (?:an opponent's attack during (?:his or her|their) last turn|an attack during your opponent's last turn), this attack does (\d+) more damage\.", text)
            if m:
                for ko in (False, True):
                    def setup(t, me, opp, ko=ko):
                        if ko:
                            entry = {"archetype_id": me.archetype_id, "subtypes": [], "pokemon_types": []}
                            t.state.kos_suffered_last_turn = {P1: [dict(entry)]}
                            t.state.kos_by_attack_last_turn = {P1: [dict(entry)]}
                    got = await self.run_case(ref, a.title, True, setup)
                    checked += 1
                    want = base + (int(m[1]) if ko else 0)
                    if got != want:
                        bad.append((ref, a.title, f'ko={ko}', got, want))
                continue
            m = re.fullmatch(r"if you have any (lightning|fairy|metal) pokémon on your bench, this attack does (\d+) more damage\.", text)
            if m:
                benchmate = {'lightning': 'SL.Minun_34', 'fairy': 'XY1.Spritzee_92',
                             'metal': 'SM9.Bronzong_101'}[m[1]]
                for have in (False, True):
                    def setup(t, me, opp, have=have):
                        t.put(benchmate if have else self.filler, P1, 'bench')
                    got = await self.run_case(ref, a.title, True, setup)
                    checked += 1
                    want = base + (int(m[2]) if have else 0)
                    if got != want:
                        bad.append((ref, a.title, f'bench {m[1]}={have}', got, want))
                continue
            res = await self.more_families(ref, a, text, base)
            if res is not None:
                checked += res[0]
                bad.extend(res[1])
        print(f'\nformula sweep: {checked} checks, {len(bad)} mismatches')
        for b in bad:
            print('  MISMATCH', b)
        self.assertEqual(bad, [])


async def _more_families(self, ref, a, text, base):
    """Second batch of wordings. Returns (checks, mismatches) or None."""
    bad, checked = [], 0

    async def case(label, want, setup=None, heads=True):
        nonlocal checked
        got = await self.run_case(ref, a.title, heads, setup)
        checked += 1
        if got != want:
            bad.append((ref, a.title, label, got, want))

    m = re.fullmatch(r"if (there is any stadium card in play|a stadium is in play|you have (?:any stadium card|a stadium) in play), this attack does (\d+) more damage\.", text)
    if m:
        own = m[1].startswith('you have')
        await case('no stadium', base)
        await case('own stadium', base + int(m[2]),
                   lambda t, me, opp: t.stadium('SWSH7.StormyMountains_232', P1))
        await case('opponent stadium', base + (0 if own else int(m[2])),
                   lambda t, me, opp: t.stadium('SWSH7.StormyMountains_232', P2))
        return checked, bad
    m = re.fullmatch(r"if this pokémon was healed during this turn, this attack does (\d+) more damage\.", text)
    if m:
        await case('not healed', base)
        await case('healed', base + int(m[1]),
                   lambda t, me, opp: t.state.healed_entities.add(me.entity_id))
        return checked, bad
    m = re.fullmatch(r"this attack does (\d+) damage for each prize card your opponent has taken\.", text)
    if m:
        await case('2 taken', 2 * int(m[1]), lambda t, me, opp: t.set_prizes(P2, 4))
        return checked, bad
    m = re.fullmatch(r"(?:this attack )?does (\d+) (more )?damage for each pokémon in your discard pile\.", text)
    if m:
        def setup(t, me, opp):
            for _ in range(3):
                t.put(self.filler, P1, 'discard')
        await case('3 in discard', (base if m[2] else 0) + 3 * int(m[1]), setup)
        return checked, bad
    m = re.fullmatch(r"(?:this attack )?does (\d+) (more )?damage for each (?:(grass|fire|water|lightning|psychic|fighting|darkness|metal) )?energy attached to this pokémon\.", text)
    if m:
        kind = getattr(PokemonTypes, m[3].upper()) if m[3] else None

        def setup(t, me, opp):
            if kind is not None:
                t.energy(me, kind, 2)
            else:
                t.energy(me, D, 1)
        t, me, opp = self.ready(ref, a.title)
        setup(t, me, opp)
        n = sum(1 for c in me.children
                for o in [energy_provided_options(t.board, c)] if o
                and (kind is None or any(kind.value in x for x in o)))
        await case(f'{n} energy', (base if m[2] else 0) + n * int(m[1]), setup)
        return checked, bad
    m = re.fullmatch(r"if this pokémon has (?:any|a) special energy attached(?: to it)?, this attack does (\d+) more damage\.", text)
    if m:
        await case('no special', base)
        await case('special', base + int(m[1]),
                   lambda t, me, opp: t.attach('BW6.BlendEnergyGrassFirePsychicDarkness_117', me))
        return checked, bad
    m = re.fullmatch(r"if your opponent's active pokémon has any special energy attached(?: to it)?, this attack does (\d+) more damage\.", text)
    if m:
        await case('no special', base)
        await case('special', base + int(m[1]),
                   lambda t, me, opp: t.attach('BW6.BlendEnergyGrassFirePsychicDarkness_117', opp))
        return checked, bad
    m = re.fullmatch(r"(?:this attack )?does (\d+) (more )?damage (?:times the number of cards|for each card) in your hand\.", text)
    if m:
        def setup(t, me, opp):
            for _ in range(4):
                t.put(self.item, P1, 'hand')
        await case('4 in hand', (base if m[2] else 0) + 4 * int(m[1]), setup)
        return checked, bad
    m = re.fullmatch(r"this attack does (\d+) damage for each energy attached to all of your opponent's pokémon\.", text)
    if m:
        def setup(t, me, opp):
            t.energy(opp, D, 1)
            t.energy(t.opp_bench, D, 2)
        await case('3 opp energy', 3 * int(m[1]), setup)
        return checked, bad
    m = re.fullmatch(r"if you have the same number of cards in your hand as your opponent, this attack does (\d+) more damage\.", text)
    if m:
        def same(t, me, opp, n=2):
            for _ in range(2):
                t.put(self.item, P1, 'hand')
            for _ in range(n):
                t.put(self.item, P2, 'hand')
        await case('same', base + int(m[1]), same)
        await case('different', base, lambda t, me, opp: same(t, me, opp, 3))
        return checked, bad
    return await _third_families(self, ref, a, text, base, case, bad, lambda: checked)


RULE_BOX = {'a pokémon ex': ['ex'], 'a pokémon-ex': ['EX'], 'a pokémon v': ['V'],
            'a pokémon-gx': ['GX']}


async def _third_families(self, ref, a, text, base, case, bad, checked):
    from contextlib import contextmanager
    from spirit.game.data_utils import def_for

    def swap_defender(t, spec, hp=400):
        t.board.find_player_area(P2, 'activePokemonArea').remove_child(t.active(P2))
        new = neutral(t.put(spec, P2, 'active'), hp=hp)
        t.new_opp = new
        return new

    @contextmanager
    def subtypes(spec, extra):
        d = fixtures.definition(spec)
        saved = list(d.subtypes)
        d.subtypes[:] = saved + extra
        try:
            yield
        finally:
            d.subtypes[:] = saved

    async def vs(spec, want, label, setup=None, extra=()):
        t, me, opp = self.ready(ref, a.title)
        neutral(me, hp=300)
        new = swap_defender(t, spec)
        if setup:
            setup(t, me, new)
        t.heads = True
        with subtypes(spec, list(extra)):
            await t.attack(me, a.title)
        got = 400 - t.hp(new)
        if got != want:
            bad.append((ref, a.title, label, got, want))
        return 1

    n = 0
    m = re.fullmatch(r"if (?:your opponent's active pokémon|the defending pokémon) is (a pokémon ex|a pokémon-ex|a pokémon v)(?: or (pokémon v|pokémon-gx|a pokémon-gx|a pokémon-ex))?, this attack does (\d+) more damage(?: \(before applying weakness and resistance\))?\.", text)
    if m:
        kinds = [RULE_BOX[m[1]]]
        if m[2]:
            kinds.append(RULE_BOX['a ' + m[2] if not m[2].startswith('a ') else m[2]])
        n += await vs('SL.Minun_34', base, 'plain basic')
        for extra in kinds:
            n += await vs('SL.Minun_34', base + int(m[3]), f'rule box {extra}', extra=extra)
        return n, bad
    m = re.fullmatch(r"if your opponent's active pokémon is a pokémon-gx or a pokémon-ex, this attack does (\d+) more damage \(before applying weakness and resistance\)\.", text)
    if m:
        n += await vs('SL.Minun_34', base, 'plain')
        n += await vs('SL.Minun_34', base + int(m[1]), 'GX', extra=['GX'])
        n += await vs('SL.Minun_34', base + int(m[1]), 'EX', extra=['EX'])
        return n, bad
    m = re.fullmatch(r"if (?:your opponent's active pokémon|the defending pokémon) already has any damage counters on it, this attack does (\d+) more damage\.", text)
    if m:
        n += await vs('SL.Minun_34', base, 'undamaged')
        n += await vs('SL.Minun_34', base + int(m[1]) + 10, 'damaged (10 already on it)',
                      lambda t, me, o: o.set_attribute(AttrID.HP, 390))
        return n, bad
    m = re.fullmatch(r"(?:this attack )?does (\d+) more damage (?:for each|times the number of) (?:of )?your opponent's benched pokémon\.", text)
    if m:
        def setup(t, me, opp):
            t.put(self.filler, P2, 'bench')
        await case('2 opp bench', base + 2 * int(m[1]), setup)
        return checked(), bad
    m = re.fullmatch(r"(?:this attack )?does (\d+) damage (?:for each|times the number) of your benched pokémon\.", text)
    if m:
        def setup(t, me, opp):
            t.put(self.filler, P1, 'bench'); t.put(self.filler, P1, 'bench')
        await case('2 own bench', 2 * int(m[1]), setup)
        return checked(), bad
    m = re.fullmatch(r"(?:this attack )?does (\d+) more damage for each damage counter on (?:your opponent's active pokémon|the defending pokémon)\.", text)
    if m:
        await case('3 counters', base + 3 * int(m[1]),
                   lambda t, me, opp: opp.set_attribute(AttrID.HP, 370))
        return checked(), bad
    m = re.fullmatch(r"(?:this attack )?does (\d+) (more )?damage for each damage counter on all of your opponent's pokémon\.", text)
    if m:
        def setup(t, me, opp):
            opp.set_attribute(AttrID.HP, 380); t.opp_bench.set_attribute(AttrID.HP, 370)
        await case('5 counters (2 already on the Active)', (base if m[2] else 0) + 5 * int(m[1]) + 20, setup)
        return checked(), bad
    m = re.fullmatch(r"flip a coin for each (?:(grass|fire|water|lightning|psychic|fighting|darkness|metal) )?energy attached to this pokémon\. this attack does (\d+) damage (?:for each heads|times the number of heads)\.", text)
    if m:
        t, me, opp = self.ready(ref, a.title)
        kind = getattr(PokemonTypes, m[1].upper()) if m[1] else None
        k = sum(1 for c in me.children for o in [energy_provided_options(t.board, c)]
                if o and (kind is None or any(kind.value in x for x in o)))
        await case(f'{k} coins all heads', k * int(m[2]), heads=True)
        return checked(), bad
    m = re.fullmatch(r"flip a coin\. if heads, this attack does (\d+) more damage,? and heal (\d+) damage from this pokémon\.", text)
    if m:
        def hurt(t, me, opp):
            me.set_attribute(AttrID.HP, 200)
        t, me, opp = self.ready(ref, a.title)
        neutral(me, hp=300); hurt(t, me, opp)
        t.heads = True
        await t.attack(me, a.title)
        got = (400 - t.hp(opp), t.hp(me))
        want = (base + int(m[1]), 200 + int(m[2]))
        if got != want:
            bad.append((ref, a.title, 'heads', got, want))
        return checked() + 1, bad
    m = re.fullmatch(r"if your opponent has any (grass|fire|water|lightning|psychic|fighting|darkness|metal|fairy|dragon) pokémon in play, this attack does (\d+) more damage\.", text)
    if m:
        kind = getattr(PokemonTypes, m[1].upper())
        await case('none', base)
        await case('on bench', base + int(m[2]),
                   lambda t, me, opp: t.opp_bench.set_attribute(AttrID.POKEMON_TYPES, [kind.value]))
        return checked(), bad
    m = re.fullmatch(r"if (?:your opponent's active pokémon|the defending pokémon) has (grass|fire|water|lightning|psychic|fighting|darkness|metal|fairy) resistance, this attack does (\d+) more damage\.", text)
    if m:
        kind = getattr(PokemonTypes, m[1].upper())
        await case('no resistance', base)
        await case('resistance', base + int(m[2]),
                   lambda t, me, opp: opp.set_attribute(AttrID.RESISTANCE_TYPES, [kind.value]))
        return checked(), bad
    m = re.fullmatch(r"if (?:your opponent's active pokémon|the defending pokémon) has no retreat cost, this attack does (\d+) more damage\.", text)
    if m:
        await case('cost 1', base, lambda t, me, opp: opp.set_attribute(AttrID.RETREAT_COST, 1))
        await case('cost 0', base + int(m[1]), lambda t, me, opp: opp.set_attribute(AttrID.RETREAT_COST, 0))
        return checked(), bad
    m = re.fullmatch(r"if this pokémon was on the bench and became your active pokémon this turn, this attack does (\d+) more damage\.", text)
    if m:
        await case('not moved', base)
        await case('moved up', base + int(m[1]),
                   lambda t, me, opp: t.state.became_active_turn.__setitem__(me.entity_id, t.state.turn_number))
        return checked(), bad
    m = re.fullmatch(r"if there are (\d+) or fewer cards in your deck, this attack does (\d+) more damage\.", text)
    if m:
        lim = int(m[1])

        def thin(t, me, opp):
            deck = t.board.find_player_area(P1, 'deck')
            while len(deck.children) > lim:
                deck.remove_child(deck.children[0])
        await case('full deck', base)
        await case('thin deck', base + int(m[2]), thin)
        return checked(), bad
    m = re.fullmatch(r"if you played a supporter card from your hand during this turn, this attack does (\d+) more damage\.", text)
    if m:
        await case('no supporter', base)
        await case('supporter', base + int(m[1]),
                   lambda t, me, opp: t.state.trainers_played.append(
                       ('x', 'Tulip', TrainerType.SUPPORTER.value)))
        return checked(), bad
    m = re.fullmatch(r"if (?:your opponent's active pokémon|the defending pokémon) is an? (grass|fire|water|lightning|psychic|fighting|darkness|metal|fairy|dragon) pokémon, this attack does (\d+) more damage(?: \(before applying weakness and resistance\))?\.", text)
    if m:
        kind = getattr(PokemonTypes, m[1].upper())
        await case('other type', base)
        await case('type', base + int(m[2]),
                   lambda t, me, opp: opp.set_attribute(AttrID.POKEMON_TYPES, [kind.value]))
        return checked(), bad
    m = re.fullmatch(r"(?:this attack )?does (\d+) damage minus (\d+) damage for each colorless in (?:your opponent's active pokémon's|the defending pokémon's) retreat cost\.", text)
    if m:
        await case('retreat 2', max(0, int(m[1]) - 2 * int(m[2])),
                   lambda t, me, opp: opp.set_attribute(AttrID.RETREAT_COST, 2))
        return checked(), bad
    m = re.fullmatch(r"(?:this attack )?does (\d+) more damage for each colorless in (?:your opponent's active pokémon's|the defending pokémon's) retreat cost\.", text)
    if m:
        await case('retreat 2', base + 2 * int(m[1]),
                   lambda t, me, opp: opp.set_attribute(AttrID.RETREAT_COST, 2))
        return checked(), bad
    m = re.fullmatch(r"(?:this attack )?does (\d+) more damage for each of your benched pokémon that has any damage counters on it\.", text)
    if m:
        def setup(t, me, opp):
            t.put(self.filler, P1, 'bench', hp=10); t.put(self.filler, P1, 'bench')
        await case('1 damaged bench', base + int(m[1]), setup)
        return checked(), bad
    m = re.fullmatch(r"(?:this attack )?does (\d+) damage for each of your pokémon that has any damage counters on it\.", text)
    if m:
        def setup(t, me, opp):
            me.set_attribute(AttrID.HP, t.hp(me) - 10)
            t.put(self.filler, P1, 'bench', hp=10); t.put(self.filler, P1, 'bench')
        await case('2 damaged', 2 * int(m[1]), setup)
        return checked(), bad
    m = re.fullmatch(r"if (\w+) is on your bench, this attack does (\d+) more damage\.", text)
    if m:
        import glob
        import os
        files = [f for f in glob.glob(os.path.join(os.path.dirname(__file__), '..', 'spirit', 'game',
                                                    'scripts', 'cards', '*', m[1].capitalize() + '_*.py'))]
        if files:
            f = sorted(files)[0]
            spec = os.path.basename(os.path.dirname(f)) + '.' + os.path.basename(f)[:-3]
            await case('absent', base)
            await case('present', base + int(m[2]),
                       lambda t, me, opp: t.put(spec, P1, 'bench'))
        return checked(), bad
    return await _fourth_families(self, ref, a, text, base, case, bad, checked)


async def _fourth_families(self, ref, a, text, base, case, bad, checked):
    m = re.fullmatch(r"if this pokémon used (.+?) during your last turn, this attack does (\d+) more damage\.", text)
    if m:
        used = m[1]

        def setup(t, me, opp, title=None):
            d = fixtures.definition(ref)
            real = next((x.title for x in d.abilities if x.title.casefold() == used), used)
            t.state.attacks_prev_turn_by_player = {P1: [(me.entity_id, me.archetype_id, title or real)]}
        await case('not used', base)
        await case('used', base + int(m[2]), setup)
        await case('other attack used', base, lambda t, me, opp: setup(t, me, opp, 'Something Else'))
        return checked(), bad
    m = re.fullmatch(r"if this pokémon evolved from (\w+) during this turn, this attack does (\d+) more damage\.", text)
    if m:
        await case('not evolved this turn', base)
        return checked(), bad
    m = re.fullmatch(r"(?:this attack )?does (\d+) damage (?:for each|times the number) of (?:your pokémon in play that has|your pokémon that have|your benched pokémon that has) the (.+?) attack\.", text)
    if m:
        bench_only = 'benched' in text

        def setup(t, me, opp):
            t.put(ref, P1, 'bench'); t.put(ref, P1, 'bench')
        await case('2 more with the attack', (2 if bench_only else 3) * int(m[1]), setup)
        return checked(), bad
    m = re.fullmatch(r"(?:this attack )?does (\d+) damage (?:for each|times the number of) pokémon in your discard pile that ha(?:s|ve) the (.+?) attack\.", text)
    if m:
        def setup(t, me, opp):
            t.put(ref, P1, 'discard'); t.put(ref, P1, 'discard')
            t.put(self.filler, P1, 'discard')
        await case('2 in discard', 2 * int(m[1]), setup)
        return checked(), bad
    m = re.fullmatch(r"your opponent reveals (?:their|his or her) hand\. this attack does (\d+) damage for each (trainer|supporter) card you find there\.", text)
    if m:
        def setup(t, me, opp):
            t.put(self.item, P2, 'hand'); t.put(self.item, P2, 'hand')
            t.put('SV4.Tulip_181', P2, 'hand'); t.put(self.filler, P2, 'hand')
        await case('hand', (3 if m[2] == 'trainer' else 1) * int(m[1]), setup)
        return checked(), bad
    m = re.fullmatch(r"(?:you may )?put up to (\d+) damage counters on this pokémon\. this attack does (\d+) (more )?damage for each damage counter you placed in this way\.", text)
    if m:
        t, me, opp = self.ready(ref, a.title)
        neutral(me, hp=300)

        async def three(ctx, prompt, buttons, *args, **kw):
            return 3
        with patch.object(EffectContext, 'choose', three):
            await t.attack(me, a.title)
        placed = (300 - t.hp(me)) // 10
        got = 400 - t.hp(opp)
        want = 3 * int(m[2]) + (base if m[3] else 0)
        if (placed, got) != (3, want):
            bad.append((ref, a.title, 'chose 3', (placed, got), (3, want)))
        return checked() + 1, bad
    m = re.fullmatch(r"if you have used your gx attack, this attack does (\d+) more damage\.", text)
    if m:
        await case('gx unused', base)
        await case('gx used', base + int(m[1]), lambda t, me, opp: t.state.gx_used.add(P1))
        return checked(), bad
    m = re.fullmatch(r"(?:this attack )?does (\d+) more damage (?:for each|times the amount of) energy attached to (?:all of your opponent's pokémon|the defending pokémon)\.", text)
    if m:
        all_ = 'all of' in text

        def setup(t, me, opp):
            t.energy(opp, D, 1); t.energy(t.opp_bench, D, 2)
        await case('energy', base + (3 if all_ else 1) * int(m[1]), setup)
        return checked(), bad
    m = re.fullmatch(r"this attack does (\d+) more damage for each prize card your opponent took (?:on|during) their last turn\.", text)
    if m:
        def setup(t, me, opp):
            t.state.prizes_taken_last_turn = {P2: 2}
        t2, me2, opp2 = self.ready(ref, a.title)
        await case('none taken', base)
        return checked(), bad
    m = re.fullmatch(r"this attack does (\d+) damage for each prize card you have taken\.", text)
    if m:
        await case('2 taken', 2 * int(m[1]), lambda t, me, opp: t.set_prizes(P1, 4))
        return checked(), bad
    m = re.fullmatch(r"this attack does (\d+) more damage for each energy attached to all of your pokémon\.", text)
    if m:
        t, me, opp = self.ready(ref, a.title)
        own = len([c for c in me.children if energy_provided_options(t.board, c)])

        def setup(t, me, opp):
            t.energy(t.put(self.filler, P1, 'bench'), D, 2)
        await case('energy', base + (own + 2) * int(m[1]), setup)
        return checked(), bad
    m = re.fullmatch(r"(?:this attack )?does (\d+) (more )?damage for each (?:of your )?(basic|evolution) pokémon (?:in play|on your bench)\.", text)
    if m:
        def setup(t, me, opp):
            t.put(self.filler, P1, 'bench'); t.put('SM12.Prinplup_55', P1, 'bench')
        t, me, opp = self.ready(ref, a.title)
        from spirit.game.data_utils import subtypes_for
        me_basic = 'Basic' in subtypes_for(me.archetype_id)
        on_bench = 'on your bench' in text
        if m[3] == 'basic':
            n = 1 + (0 if on_bench or not me_basic else 1)
        else:
            n = 1 + (0 if on_bench or me_basic else 1)
        await case('bench mix', (base if m[2] else 0) + n * int(m[1]), setup)
        return checked(), bad
    m = re.fullmatch(r"if this pokémon has (\d+) or more damage counters on it, this attack does nothing\.", text)
    if m:
        k = int(m[1])
        await case('fewer', base, lambda t, me, opp: me.set_attribute(AttrID.HP, 300 - 10 * (k - 1)))
        await case('enough', 0, lambda t, me, opp: me.set_attribute(AttrID.HP, 300 - 10 * k))
        return checked(), bad
    m = re.fullmatch(r"flip a coin\. if heads, this attack does (\d+) more damage\. if tails, this pokémon does (\d+) damage to itself\.", text)
    if m:
        await case('heads', base + int(m[1]), heads=True)
        await case('tails', base, heads=False)
        return checked(), bad
    m = re.fullmatch(r"flip (\d+) coins\. this attack does (\d+) damage times the number of heads\. this pokémon is now confused\.", text)
    if m:
        await case('all heads', int(m[1]) * int(m[2]), heads=True)
        return checked(), bad
    m = re.fullmatch(r"(?:this attack )?does (\d+) more damage for each different type of basic energy attached to this pokémon\.", text)
    if m:
        t, me, opp = self.ready(ref, a.title)

        def setup(t, me, opp):
            t.energy(me, R, 1); t.energy(me, W, 1)
        t2, me2, opp2 = self.ready(ref, a.title)
        setup(t2, me2, opp2)
        types = set()
        for c in me2.children:
            for o in energy_provided_options(t2.board, c) or []:
                types.update(o)
        types.discard(PokemonTypes.COLORLESS.value)
        await case('types', base + len(types) * int(m[1]), setup)
        return checked(), bad
    return None


FormulaSweep.more_families = _more_families


async def _const(v):
    return v


if __name__ == '__main__':
    unittest.main()
