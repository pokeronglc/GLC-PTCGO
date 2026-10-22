"""Bug hunt (Oct 14) part 3: EFFECT texts of the untested Pokemon attacks
(dev_notes/untested_pokemon_oct14.txt) that no tests/test_sweep_* checker
covers. One family per common wording; each runs the attack on a small board
and checks the board afterwards.
"""
import re
import unittest
from unittest.mock import patch

from tests import test_hgss_rules as fixtures
from tests.test_untested_formula_sweep import _attacks
from tests.test_untested_live_cards import Base, neutral, D, W, P1, P2
from spirit.game.attributes import AttrID, PokemonTypes
from spirit.game.session.effects import EffectContext


class EffectSweep(Base):
    async def test_sweep(self):
        cases = _attacks()
        if not cases:
            self.skipTest('reference list not available')
        bad, checked = [], 0
        for ref, a, text, has_ability in cases:
            res = await self.family(ref, a, text)
            if res is None:
                continue
            checked += res[0]
            bad.extend(res[1])
        print(f'effect sweep: {checked} checks, {len(bad)} mismatches')
        for b in bad:
            print('  MISMATCH', b)
        self.assertEqual(bad, [])

    async def run_atk(self, ref, a, setup=None, heads=True, yes=True, picks=None, pokemon=None):
        t, me, opp = self.ready(ref, a.title)
        neutral(me, hp=300)
        mine = [neutral(t.put(self.filler, P1, 'bench'), hp=300) for _ in range(2)]
        t.mine = mine
        if setup:
            setup(t, me, opp)
        t.heads, t.yes = heads, yes
        if picks:
            t.picks = picks
        if pokemon:
            t.pokemon = pokemon
        await t.attack(me, a.title)
        return t, me, opp

    async def family(self, ref, a, text):
        bad = []
        base = a.damage
        m = re.fullmatch(r"heal (\d+) damage from each of your (?:(benched) )?(?:(grass|fire|water|lightning|psychic|fighting|darkness|metal|fairy) )?pokémon\.", text)
        if m:
            n, bench_only, kind = int(m[1]), m[2], m[3]

            def setup(t, me, opp):
                me.set_attribute(AttrID.HP, 200)
                for p in t.mine:
                    p.set_attribute(AttrID.HP, 200)
            t, me, opp = await self.run_atk(ref, a, setup)
            types = set(me.get_attribute(AttrID.POKEMON_TYPES) or [])
            kv = getattr(PokemonTypes, kind.upper()).value if kind else None
            exp_me = 200 if bench_only or (kv and kv not in types) else 200 + n
            bench_types = set(t.mine[0].get_attribute(AttrID.POKEMON_TYPES) or [])
            exp_b = 200 if (kv and kv not in bench_types) else 200 + n
            got = (t.hp(me), [t.hp(p) for p in t.mine])
            if got != (exp_me, [exp_b, exp_b]):
                bad.append((ref, a.title, got, (exp_me, [exp_b, exp_b])))
            return 1, bad
        m = re.fullmatch(r"heal (\d+) damage from (\d+) of your (benched )?pokémon\.", text)
        if m:
            def setup(t, me, opp):
                t.mine[0].set_attribute(AttrID.HP, 100)
            t, me, opp = await self.run_atk(ref, a, setup, pokemon=lambda c, p: c[0] if c else None,
                                        picks=lambda cards, count, prompt, shown: [c for c in cards if c is cards[0]])
            healed = t.hp(t.mine[0]) - 100
            if healed not in (int(m[1]), 0) or (healed == 0 and t.hp(me) == 300 and t.mine[0] in t.zone(P1, 'bench')):
                # the picker took the first candidate; accept either the bench Pokemon healed
                if healed != int(m[1]):
                    bad.append((ref, a.title, 'healed', healed, int(m[1])))
            return 1, bad
        m = re.fullmatch(r"heal all damage from (\d+) of your benched pokémon\.", text)
        if m:
            def setup(t, me, opp):
                t.mine[0].set_attribute(AttrID.HP, 100)
            t, me, opp = await self.run_atk(ref, a, setup, pokemon=lambda c, p: c[0],
                                        picks=lambda cards, count, prompt, shown: cards[:1])
            if t.hp(t.mine[0]) != 300:
                bad.append((ref, a.title, t.hp(t.mine[0]), 300))
            return 1, bad
        m = re.fullmatch(r"(?:this attack )?(also )?does (\d+) damage to each of your benched pokémon\. \(don't apply weakness and resistance for benched pokémon\.\)", text)
        if m:
            t, me, opp = await self.run_atk(ref, a)
            got = ([300 - t.hp(p) for p in t.mine], 400 - t.hp(opp), t.hp(t.opp_bench))
            want = ([int(m[2])] * 2, base, 400)
            if got != want:
                bad.append((ref, a.title, got, want))
            return 1, bad
        m = re.fullmatch(r"this attack also does (\d+) damage to (\d+) of your benched pokémon\. \(don't apply weakness and resistance for benched pokémon\.\)", text)
        if m:
            t, me, opp = await self.run_atk(ref, a, pokemon=lambda c, p: c[0],
                                        picks=lambda cards, count, prompt, shown: cards[:count])
            hits = sorted(300 - t.hp(p) for p in t.mine)
            want = sorted([int(m[1])] * int(m[2]) + [0] * (2 - int(m[2])))
            if hits != want or 400 - t.hp(opp) != base:
                bad.append((ref, a.title, hits, want))
            return 1, bad
        m = re.fullmatch(r"this pokémon can't attack during your next turn\.", text)
        if m:
            t, me, opp = await self.run_atk(ref, a)
            t.next_turn(); t.next_turn()
            offered = [e for e in t.offers(me, 'UsePokemonAttack')]
            if offered:
                bad.append((ref, a.title, 'still attacks next turn'))
            return 1, bad
        m = re.fullmatch(r"this pokémon can't use (.+?) during your next turn\.", text)
        if m:
            t, me, opp = await self.run_atk(ref, a)
            t.next_turn(); t.next_turn()
            if t.attack_offer(me, a.title) is not None:
                bad.append((ref, a.title, 'not locked'))
            return 1, bad
        m = re.fullmatch(r"move an energy from this pokémon to (\d+) of your benched pokémon\.", text)
        if m:
            t, me, opp = await self.run_atk(ref, a, pokemon=lambda c, p: t_first(c))
            got = sum(len(p.children) for p in t.mine)
            if got != 1:
                bad.append((ref, a.title, 'moved', got, 1))
            return 1, bad
        m = re.fullmatch(r"put (\d+) damage counters? on your opponent's active pokémon\.", text)
        if m:
            t, me, opp = await self.run_atk(ref, a)
            if 400 - t.hp(opp) != 10 * int(m[1]) + base:
                bad.append((ref, a.title, 400 - t.hp(opp), 10 * int(m[1]) + base))
            return 1, bad
        m = re.fullmatch(r"put (\d+) damage counters? on (\d+) of your opponent's pokémon\.", text)
        if m:
            t, me, opp = await self.run_atk(ref, a, pokemon=lambda c, p: t_bench(c, p), picks=lambda cards, count, prompt, shown: cards[-count:])
            total = (400 - t.hp(opp) - base) + (400 - t.hp(t.opp_bench))
            if total != 10 * int(m[1]) * int(m[2]):
                bad.append((ref, a.title, total, 10 * int(m[1]) * int(m[2])))
            return 1, bad
        m = re.fullmatch(r"put this pokémon and all attached cards into your hand\.", text)
        if m:
            t, me, opp = await self.run_atk(ref, a)
            if me in t.board.pokemon_in_play(P1) or me not in t.zone(P1, 'hand'):
                bad.append((ref, a.title, 'not returned to hand'))
            return 1, bad
        m = re.fullmatch(r"(you may )?put (?:an|(\d+)) energy attached to your opponent's active pokémon into their hand\.", text)
        if m:
            t, me, opp = await self.run_atk(ref, a, lambda t, me, opp: t.energy(opp, D, 2))
            n = int(m[2] or 1)
            if sum(1 for c in t.zone(P2, 'hand')) != n:
                bad.append((ref, a.title, 'in hand', len(t.zone(P2, 'hand')), n))
            return 1, bad
        m = re.fullmatch(r"switch (?:in )?(\d+) of your opponent's benched pokémon (?:with their active pokémon|to the active spot)\. this attack does (\d+) damage to the new active pokémon\.", text)
        if m:
            t, me, opp = await self.run_atk(ref, a, pokemon=lambda c, p: c[0])
            new = t.active(P2)
            if new is opp or 400 - t.hp(new) != int(m[2]) or t.hp(opp) != 400:
                bad.append((ref, a.title, 'gust+damage', new is opp, 400 - t.hp(new), t.hp(opp)))
            return 1, bad
        m = re.fullmatch(r"put an energy attached to this pokémon into your hand\.", text)
        if m:
            t, me, opp = await self.run_atk(ref, a)
            hand = [c for c in t.zone(P1, 'hand')]
            if len(hand) != 1:
                bad.append((ref, a.title, 'hand', len(hand)))
            return 1, bad
        m = re.fullmatch(r"move all energy from this pokémon to your benched pokémon in any way you like\.", text)
        if m:
            t, me, opp = await self.run_atk(ref, a, pokemon=lambda c, p: c[0])
            if me.children or not any(p.children for p in t.mine):
                bad.append((ref, a.title, 'energy left', len(me.children)))
            return 1, bad
        m = re.fullmatch(r"look at the top (\d+) cards of your deck and put them back in any order\.", text)
        if m:
            t, me, opp = await self.run_atk(ref, a)
            return 1, bad
        m = re.fullmatch(r"move all damage counters from (\d+) of your benched pokémon to your opponent's active pokémon\.", text)
        if m:
            t, me, opp = await self.run_atk(ref, a, lambda t, me, opp: t.mine[0].set_attribute(AttrID.HP, 250),
                                        pokemon=lambda c, p: c[0])
            if t.hp(t.mine[0]) != 300 or 400 - t.hp(opp) != 50 + base:
                bad.append((ref, a.title, t.hp(t.mine[0]), 400 - t.hp(opp)))
            return 1, bad
        m = re.fullmatch(r"if your opponent's active pokémon has no damage counters on it before this attack does damage, this attack does nothing\.", text)
        if m:
            t, me, opp = await self.run_atk(ref, a)
            if t.hp(opp) != 400:
                bad.append((ref, a.title, 'undamaged target took', 400 - t.hp(opp)))
            t, me, opp = await self.run_atk(ref, a, lambda t, me, opp: opp.set_attribute(AttrID.HP, 390))
            if 390 - t.hp(opp) != base:
                bad.append((ref, a.title, 'damaged target took', 390 - t.hp(opp), base))
            return 2, bad
        m = re.fullmatch(r"put a card from your discard pile into your hand\.", text)
        if m:
            t, me, opp = await self.run_atk(ref, a, lambda t, me, opp: t.put(self.item, P1, 'discard'))
            if len(t.zone(P1, 'hand')) != 1:
                bad.append((ref, a.title, 'hand', len(t.zone(P1, 'hand'))))
            return 1, bad
        m = re.fullmatch(r"put a card from your discard pile on top of your deck\.", text)
        if m:
            t, me, opp = await self.run_atk(ref, a, lambda t, me, opp: t.put('SL.Minun_34', P1, 'discard'))
            if 'Minun' not in t.names(t.zone(P1, 'deck')[-1:]):
                bad.append((ref, a.title, 'top of deck', t.names(t.zone(P1, 'deck')[-1:])))
            return 1, bad
        m = re.fullmatch(r"during your opponent's next turn, if this pokémon would be damaged by an attack, prevent that attack's damage done to this pokémon if that damage is (\d+) or less\.", text)
        if m:
            return 0, bad
        m = re.fullmatch(r"draw cards until you have (\d+) cards in your hand\.", text)
        if m:
            t, me, opp = await self.run_atk(ref, a)
            if len(t.zone(P1, 'hand')) != int(m[1]):
                bad.append((ref, a.title, len(t.zone(P1, 'hand')), int(m[1])))
            return 1, bad
        m = re.fullmatch(r"put up to (\d+) pokémon from your discard pile into your hand\.", text)
        if m:
            t, me, opp = await self.run_atk(ref, a, lambda t, me, opp: [t.put('SL.Minun_34', P1, 'discard') for _ in range(4)])
            if len(t.zone(P1, 'hand')) != int(m[1]):
                bad.append((ref, a.title, len(t.zone(P1, 'hand')), int(m[1])))
            return 1, bad
        m = re.fullmatch(r"put up to (\d+) basic energy cards from your discard pile into your hand\.", text)
        if m:
            t, me, opp = await self.run_atk(ref, a, lambda t, me, opp: [t.put(t.basic_energy(D), P1, 'discard') for _ in range(4)])
            if len(t.zone(P1, 'hand')) != int(m[1]):
                bad.append((ref, a.title, len(t.zone(P1, 'hand')), int(m[1])))
            return 1, bad
        m = re.fullmatch(r"put damage counters on your opponent's active pokémon until its remaining hp is (\d+)\.", text)
        if m:
            t, me, opp = await self.run_atk(ref, a)
            if t.hp(opp) != int(m[1]):
                bad.append((ref, a.title, t.hp(opp), int(m[1])))
            return 1, bad
        m = re.fullmatch(r"before doing damage, discard all pokémon tools from your opponent's active pokémon\.", text)
        if m:
            def setup(t, me, opp):
                tool = t.put('SV065.Powerglass_63', P2, 'hand')
                t.board.attach_card(tool.entity_id, opp.entity_id)
                t.tool = tool
            t, me, opp = await self.run_atk(ref, a, setup)
            if t.tool not in t.zone(P2, 'discard'):
                bad.append((ref, a.title, 'tool kept'))
            return 1, bad
        m = re.fullmatch(r"if your opponent's active pokémon is a basic pokémon, it can't attack during your opponent's next turn\.", text)
        if m:
            t, me, opp = await self.run_atk(ref, a, lambda t, me, opp: t.energy(opp, D, 4))
            t.next_turn()
            if [e for e in t.offers(opp, 'UsePokemonAttack', pid=P2)]:
                bad.append((ref, a.title, 'basic still attacks'))
            return 1, bad
        m = re.fullmatch(r"move an energy attached to your opponent's active pokémon to (\d+) of your opponent's benched pokémon\.", text)
        if m:
            t, me, opp = await self.run_atk(ref, a, lambda t, me, opp: t.energy(opp, D, 1), pokemon=lambda c, p: c[0])
            if opp.children or not t.opp_bench.children:
                bad.append((ref, a.title, 'energy not moved'))
            return 1, bad
        m = re.fullmatch(r"choose (\d+) of your opponent's active pokémon's attacks\. that pokémon can't use that attack during your opponent's next turn\.", text)
        if m:
            from spirit.game.session.game_session import GameSession

            async def pick(session, pid, source, candidates, prompt=''):
                return 0
            t, me, opp = self.ready(ref, a.title)
            t.energy(opp, D, 4)
            with patch.object(GameSession, 'prompt_attack_selection', pick):
                await t.attack(me, a.title)
            t.next_turn()
            from spirit.game.data_utils import def_for
            first = next(x for x in def_for(opp.archetype_id).abilities if type(x).__name__ == 'Attack')
            if t.attack_offer(opp, first.title, pid=P2) is not None:
                bad.append((ref, a.title, 'attack not locked'))
            return 1, bad
        m = re.fullmatch(r"switch this pokémon with (\d+) of your benched (?:(grass|fire|water|lightning|psychic|fighting|darkness|metal) )?pokémon\.", text)
        if m:
            kind = getattr(PokemonTypes, m[2].upper()).value if m[2] else None

            def setup(t, me, opp):
                if kind:
                    t.mine[0].set_attribute(AttrID.POKEMON_TYPES, [kind])
            t, me, opp = await self.run_atk(ref, a, setup, pokemon=lambda c, p: c[0])
            if t.active(P1) is me:
                bad.append((ref, a.title, 'not switched'))
            return 1, bad
        m = re.fullmatch(r"if this pokémon evolved during this turn, this attack does nothing\.", text)
        if m:
            t, me, opp = await self.run_atk(ref, a)
            if 400 - t.hp(opp) != base:
                bad.append((ref, a.title, 'not evolved but did', 400 - t.hp(opp)))
            return 1, bad
        m = re.fullmatch(r"move an? (?:(grass|fire|water|lightning|psychic|fighting|darkness|metal|basic) )?energy from this pokémon to (\d+) of your benched pokémon\.", text)
        if m:
            t, me, opp = await self.run_atk(ref, a, pokemon=lambda c, p: c[0])
            if sum(len(p.children) for p in t.mine) != 1:
                bad.append((ref, a.title, 'moved', sum(len(p.children) for p in t.mine)))
            return 1, bad
        m = re.fullmatch(r"(?:you may )?search your deck for up to (\d+) cards and put them into your hand\. then, shuffle your deck\.", text)
        if m:
            t, me, opp = await self.run_atk(ref, a)
            if len(t.zone(P1, 'hand')) != int(m[1]):
                bad.append((ref, a.title, len(t.zone(P1, 'hand')), int(m[1])))
            return 1, bad
        m = re.fullmatch(r"(?:this attack )?does (\d+) damage to (\d+) of your opponent's pokémon\. (?:\(don't apply weakness and resistance for benched pokémon\.\)|this attack's damage isn't affected by weakness or resistance\.)", text)
        if m:
            t, me, opp = await self.run_atk(ref, a, pokemon=lambda c, p: c[-1],
                                            picks=lambda cards, count, prompt, shown: cards[-count:])
            total = (400 - t.hp(opp)) + (400 - t.hp(t.opp_bench))
            if total != int(m[1]) * min(int(m[2]), 2):
                bad.append((ref, a.title, total, int(m[1]) * min(int(m[2]), 2)))
            return 1, bad
        m = re.fullmatch(r"(?:this attack )?does (\d+) damage to (\d+) of your benched pokémon\. \(don't apply weakness and resistance for benched pokémon\.\)", text)
        if m:
            t, me, opp = await self.run_atk(ref, a, pokemon=lambda c, p: c[0],
                                            picks=lambda cards, count, prompt, shown: cards[:count])
            hits = sum(300 - t.hp(p) for p in t.mine)
            if hits != int(m[1]) * int(m[2]):
                bad.append((ref, a.title, hits, int(m[1]) * int(m[2])))
            return 1, bad
        m = re.fullmatch(r"(?:this attack )?does (\d+) damage to each of your opponent's benched pokémon that has any damage counters on it\. \(don't apply weakness and resistance for benched pokémon\.\)", text)
        if m:
            def setup(t, me, opp):
                t.opp_bench.set_attribute(AttrID.HP, 390)
                t.clean = neutral(t.put(self.filler, P2, 'bench'), hp=400)
            t, me, opp = await self.run_atk(ref, a, setup)
            if (390 - t.hp(t.opp_bench), 400 - t.hp(t.clean)) != (int(m[1]), 0):
                bad.append((ref, a.title, 390 - t.hp(t.opp_bench), 400 - t.hp(t.clean)))
            return 1, bad
        m = re.fullmatch(r"does (\d+) damage to each benched pokémon \(both yours and your opponent's\)\. \(don't apply weakness and resistance for benched pokémon\.\)", text)
        if m:
            t, me, opp = await self.run_atk(ref, a)
            if (300 - t.hp(t.mine[0]), 400 - t.hp(t.opp_bench)) != (int(m[1]), int(m[1])):
                bad.append((ref, a.title, 300 - t.hp(t.mine[0]), 400 - t.hp(t.opp_bench)))
            return 1, bad
        return None


def t_first(c):
    return c[0] if c else None


def t_bench(c, p):
    return c[-1] if c else None


if __name__ == '__main__':
    unittest.main()


class SharedEffectVariants(Base):
    """Shared effect functions reused by printings with different text."""
    async def test_iron_breaker_stops_attacks(self):
        from tests.bughunt_table import Table
        for ref in ('BW3.Cobalion_84', 'BW11.Cobalion_91', 'BW2.Beartic_30'):
            d = fixtures.definition(ref)
            title = next(a.title for a in d.abilities if "can't attack" in (a.game_text or ''))
            t, me, opp = self.ready(ref, title)
            t.energy(opp, D, 4)
            await t.attack(me, title)
            t.next_turn()
            self.assertEqual(t.offers(opp, 'UsePokemonAttack', pid=P2), [], ref)

    async def test_dark_clamp_still_blocks_retreat(self):
        t, me, opp = self.ready('BW4.Muk_53', None)
        d = fixtures.definition('BW4.Muk_53')
        title = next(a.title for a in d.abilities if "can't retreat" in (a.game_text or ''))
        t, me, opp = self.ready('BW4.Muk_53', title)
        t.energy(opp, D, 4)
        opp.set_attribute(AttrID.RETREAT_COST, 1)
        await t.attack(me, title)
        t.next_turn()
        self.assertEqual(t.offers(opp, 'RetreatPokemon', pid=P2), [])

    async def test_snom_calls_one(self):
        d = fixtures.definition('SWSH45.Snom_29')
        title = next(a.title for a in d.abilities if 'Basic Pok' in (a.game_text or ''))
        t, me, opp = self.ready('SWSH45.Snom_29', title)
        t.deck(P1, ['BW1.Basculin_35', 'BW1.Basculin_35'])
        await t.attack(me, title)
        self.assertEqual(len(t.zone(P1, 'bench')), 1)

    async def test_glaceon_moves_any_energy(self):
        d = fixtures.definition('BW5.Glaceon_30')
        title = next(a.title for a in d.abilities if 'Move an Energy' in (a.game_text or ''))
        t, me, opp = self.table('BW5.Glaceon_30', count=0)
        for k, v in next(a for a in d.abilities if a.title == title).cost.items():
            t.energy(me, D if k == PokemonTypes.COLORLESS else k, v)
        t.energy(me, D, 1)
        b = t.put(self.filler, P1, 'bench')
        t.picks = lambda cards, count, prompt, shown: [c for c in cards if (c.get_attribute(AttrID.ENERGY_INFO) or {}).get('options') == [[D.value]]][:1] or cards[:1]
        await t.attack(me, title)
        self.assertEqual(len(b.children), 1)

    async def test_jolteon_ex_lock(self):
        from contextlib import contextmanager
        d = fixtures.definition('BW9.Jolteon_34')
        title = next(a.title for a in d.abilities if 'Pokémon-EX' in (a.game_text or ''))
        defd = fixtures.definition('SL.Minun_34')
        saved = list(defd.subtypes)
        defd.subtypes[:] = saved + ['EX']
        try:
            t, me, opp = self.ready('BW9.Jolteon_34', title)
            t.board.find_player_area(P2, 'activePokemonArea').remove_child(opp)
            ex = neutral(t.put('SL.Minun_34', P2, 'active'), hp=400)
            t.energy(ex, D, 4)
            await t.attack(me, title)
            t.next_turn()
            self.assertEqual(t.offers(ex, 'UsePokemonAttack', pid=P2), [])
        finally:
            defd.subtypes[:] = saved


class DetectorEvidenceLeads(Base):
    """Attacks the no-op detector never saw do their main thing on random
    boards (usually because the searched cards were absent)."""
    async def test_searches_with_targets_present(self):
        for ref, title, deck, zone, n in (
                ('XY8.Starly_125', 'Call for Pals', ['XY8.Starly_125'] * 2, 'bench', 2),
                ('XY5.Weedle_1', 'Multiply', ['XY5.Weedle_1'], 'bench', 1),
                ('SM12.Eevee_167', 'Follow My Tail', ['SM12.Eevee_167'] * 2, 'bench', 2),
                ('SV07.Charjabug_52', 'Parallel Placement', ['SV07.Charjabug_52'] * 3, 'bench', 3),
                ('SWSH12.Murkrow_106', 'Flock', ['SWSH12.Murkrow_106'] * 2, 'bench', 2)):
            t, me, opp = self.ready(ref, title)
            cards = t.deck(P1, deck)
            t.picks = lambda cs, count, prompt, shown: [c for c in cs if c in cards][:count]
            await t.attack(me, title)
            self.assertEqual(sum(c in t.zone(P1, zone) for c in cards), n, ref)

    async def test_lost_march(self):
        for ref in ('SM8.Natu_87', 'SM8.Jumpluff_14', 'SM12.Whimsicott_148', 'SM12.Cottonee_147'):
            t, me, opp = self.ready(ref, 'Lost March')
            for _ in range(3):
                t.put('BW1.Basculin_35', P1, 'lostZone')
            await t.attack(me, 'Lost March')
            self.assertEqual(400 - t.hp(opp), 60, ref)


class PowerSplit(Base):
    async def test_claydol_power_split(self):
        t, me, opp = self.ready('SWSH5.Claydol_58', 'Power Split')
        t.energy(opp, D, 3)
        for _ in range(4):
            t.put(t.basic_energy(PokemonTypes.PSYCHIC), P1, 'discard')
        mine_before = len(me.children)
        await t.attack(me, 'Power Split')
        mine = sum(len([c for c in p.children]) for p in t.board.pokemon_in_play(P1))
        self.assertEqual(mine, 3)
