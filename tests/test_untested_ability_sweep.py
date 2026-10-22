"""Bug hunt 3 (Oct 14): Pokemon Abilities no test named.

List: dev_notes/untested_abilities_oct14.txt (module | title | text).  Each
family below matches a printed wording and checks every card that uses it on
a real board (real attacks, real retreat/HP/condition queries).  A family
prints MISMATCH lines and fails with the list.
"""
import os
import re
import unittest

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table
from tests.untested_trainer_kit import (
    C, G, R, W, L, P, F, D, M, Y, N, big, board, neutral, plain, plain_attack, pay,
    max_hp, weak_to)
from spirit.game.attributes import AttrID, PokemonTypes
from spirit.tools.effect_smoke import P1, P2

LIST = os.path.join(os.path.dirname(__file__), '..', 'dev_notes', 'untested_abilities_oct14.txt')
TYPES = {t.name.lower(): t for t in (G, R, W, L, P, F, D, M, Y, N, C)}


def rows():
    out = []
    with open(LIST, encoding='utf-8') as fh:
        for line in fh:
            if line.startswith('#') or not line.strip():
                continue
            mod, title, text = [x.strip() for x in line.split(' | ', 2)]
            out.append((mod, title, text, text.lower()))
    return out


class Sweep(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    def family(self, rx):
        return [r for r in rows() if re.search(rx, r[3])]

    def report(self, name, checked, bad):
        for b in bad:
            print('MISMATCH', name, b)
        print(f'{name}: {checked} checked, {len(bad)} mismatches')
        self.assertEqual(bad, [])

    async def hit(self, mod, attacker=None, *, active=True, setup=None, hp=400):
        """Damage a plain attack does to `mod` (P2) -- in the Active Spot or on the Bench."""
        t, a, d = board(self, attacker or big(C), None if active else None)
        target = t.put(mod, P2, 'active' if active else 'bench')
        neutral(target, hp)
        if active:
            area = t.board.find_player_area(P2, 'activePokemonArea')
            area.remove_child(d)
            t.board.add_card_to_area(d, t.board.find_player_area(P2, 'bench'))
        if setup:
            setup(t, a, target)
        before = t.hp(target)
        if active:
            await t.attack(a, t.atk.title)
        else:
            from spirit.game.session.effects import EffectContext
            ctx = EffectContext(t.session, P1, a, t.atk)
            await t._run(lambda: ctx.deal_damage(100, target=target))
        return before - t.hp(target), t, a, target

    async def test_takes_less_damage(self):
        bad, n = [], 0
        rx = r"^this pokémon takes (\d+) less damage from attacks \(after applying weakness and resistance\)\.$|" \
             r"^any damage done to this pokémon by attacks is reduced by (\d+) \(after applying weakness and resistance\)\.$"
        for mod, title, text, low in self.family(rx):
            m = re.search(rx, low)
            less = int(m.group(1) or m.group(2))
            got, *_ = await self.hit(mod)
            atk = plain_attack(big(C)).damage
            n += 1
            if got != max(0, atk - less):
                bad.append(f'{mod} {title}: took {got}, want {atk}-{less}')
        self.report('takes-less', n, bad)

    async def test_bench_prevents_damage(self):
        bad, n = [], 0
        rx = r"^as long as this pokémon is on your bench, prevent all damage done to this pokémon by attacks"
        for mod, title, text, low in self.family(rx):
            got, *_ = await self.hit(mod, active=False)
            n += 1
            if got != 0:
                bad.append(f'{mod} {title}: Benched took {got}')
            got, *_ = await self.hit(mod, active=True)
            if got == 0:
                bad.append(f'{mod} {title}: Active took nothing')
        self.report('bench-prevent', n, bad)

    async def test_prevent_damage_from_type(self):
        bad, n = [], 0
        rx = r"^prevent all damage done to this pokémon by attacks from your opponent's (\w+) pokémon\.$"
        for mod, title, text, low in self.family(rx):
            word = re.search(rx, low).group(1)
            if word not in TYPES:
                continue
            kind = TYPES[word]
            other = R if kind != R else W
            got, *_ = await self.hit(mod, big(kind))
            got2, *_ = await self.hit(mod, big(other))
            n += 1
            if got != 0 or got2 == 0:
                bad.append(f'{mod} {title}: {kind.name} {got}, {other.name} {got2}')
        self.report('prevent-type', n, bad)

    async def test_coin_prevent(self):
        bad, n = [], 0
        rx = r"^if any damage is done to this pokémon by attacks, flip a coin\. if heads, prevent that damage\.$"
        for mod, title, text, low in self.family(rx):
            for heads in (True, False):
                got, *_ = await self.hit(mod, setup=lambda t, a, d, h=heads: setattr(t, 'heads', h))
                n += 1
                if (got == 0) != heads:
                    bad.append(f'{mod} {title}: heads={heads} took {got}')
        self.report('coin-prevent', n, bad)

    def retreat(self, mod, setup=None):
        t = Table(self)
        t.put(self.filler, P1, 'active')
        p = t.put(mod, P2, 'active')
        t.put(self.filler, P2, 'bench')
        if setup:
            setup(t, p)
        return t.retreat(p)

    async def test_energy_no_retreat(self):
        bad, n = [], 0
        rx = r"^if this pokémon has any (\w+ )?energy attached(?: to it)?, it has no retreat cost\.$"
        for mod, title, text, low in self.family(rx):
            word = (re.search(rx, low).group(1) or '').strip()
            kind = TYPES.get(word, D)
            other = R if kind != R else W
            base = self.retreat(mod)
            withit = self.retreat(mod, lambda t, p: t.energy(p, kind))
            n += 1
            if base == 0:
                continue
            if withit != 0:
                bad.append(f'{mod} {title}: with {kind.name} retreat {withit}')
            if word:
                wrong = self.retreat(mod, lambda t, p: t.energy(p, other))
                if wrong == 0:
                    bad.append(f'{mod} {title}: {other.name} Energy also freed retreat')
        rx2 = r"^if this pokémon has no energy attached to it, this pokémon has no retreat cost\.$"
        for mod, title, text, low in self.family(rx2):
            n += 1
            if self.retreat(mod) != 0:
                bad.append(f'{mod} {title}: no Energy but retreat {self.retreat(mod)}')
            if self.retreat(mod, lambda t, p: t.energy(p, D)) == 0 and fixtures.definition(mod).extra_attributes:
                from tests.untested_trainer_kit import _attr
                if (_attr(fixtures.definition(mod), AttrID.RETREAT_COST) or 0) > 0:
                    bad.append(f'{mod} {title}: Energy attached but still free')
        rx3 = r"^if there is any stadium card in play, this pokémon has no retreat cost\.$"
        for mod, title, text, low in self.family(rx3):
            n += 1
            if self.retreat(mod, lambda t, p: t.stadium('SWSH7.StormyMountains_232', P1)) != 0:
                bad.append(f'{mod} {title}: Stadium in play but retreat')
        self.report('no-retreat', n, bad)

    async def test_cant_be_condition(self):
        bad, n = [], 0
        rx = r"^this pokémon can't be (paralyzed|confused|asleep|poisoned|burned)\.$"
        for mod, title, text, low in self.family(rx):
            cond = re.search(rx, low).group(1).title()
            t = Table(self)
            me = t.put(self.filler, P1, 'active')
            p = t.put(mod, P2, 'active')
            from spirit.game.session.effects import EffectContext
            ctx = EffectContext(t.session, P1, me, None)
            from spirit.game.attributes import SpecialConditions
            await t._run(lambda: ctx.apply_special_condition(p, getattr(SpecialConditions, cond.upper())))
            n += 1
            if cond in t.conditions(p):
                bad.append(f'{mod} {title}: became {cond}')
        self.report('cant-be', n, bad)

    async def test_more_damage_to_type(self):
        bad, n = [], 0
        rx = r"^this pokémon's attacks do (\d+) more damage to your opponent's (\w+) pokémon \(before applying weakness and resistance\)\.$"
        for mod, title, text, low in self.family(rx):
            m = re.search(rx, low)
            more, kind = int(m.group(1)), TYPES[m.group(2)]
            d = fixtures.definition(mod)
            att = plain_attack(d) or next((x for x in d.abilities if type(x).__name__ == 'Attack'
                                           and (x.damage or 0) > 0 and 'flip' not in (x.game_text or '').lower()), None)
            if att is None:
                continue
            got = []
            for target in (plain(kind), plain(R if kind != R else W)):
                t, a, dd = board(self, d, target, pay_attack=False)
                pay(t, a, att)
                await t.attack(a, att.title)
                got.append(400 - t.hp(dd))
            n += 1
            if got[0] - got[1] != more:
                bad.append(f'{mod} {title}: vs {kind.name} {got[0]}, other {got[1]}')
        self.report('more-vs-type', n, bad)


if __name__ == '__main__':
    unittest.main()
