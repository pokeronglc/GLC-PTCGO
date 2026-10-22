"""Sweep: coin flips whose result matters on a LATER turn.

  * "Flip a coin. If tails, this Pokémon can't attack during your next turn"
    (and "can't use <attack>"): locked after tails, free after heads.
  * Smokescreen family: "if the Defending Pokémon tries to attack during your
    opponent's next turn, your opponent flips a coin (2 coins). If tails
    (either is tails), that attack does nothing / doesn't happen".
  * "If any damage is done to this Pokémon by attacks during your opponent's
    next turn, flip a coin. If heads, prevent that damage."
  * "If all of them are heads, ... prevent all damage ... during your
    opponent's next turn."
  * Allergy Storm (heads: no Supporters; tails: no Items).

The opponent's attacker is Dialga (Heavy Impact, 210, no text) on P2.
Report: /home/claude/bughunt/sweep/coin_next_turn.json
"""
import json
import os
import re
import unittest

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests import test_sweep_coins as sc
from tests.bughunt_table import Table
from tests.sweep_core import unique_pokemon, norm, label, pay_cost, neutral, REPORT_DIR, BIG
from spirit.game.attributes import AttrID
from spirit.game.data_utils import Attack
from spirit.tools.effect_smoke import P1, P2

OPP_ATTACKER, OPP_ATTACK, OPP_DAMAGE = 'SWSH7.Dialga_112', 'Heavy Impact', 210

SELF_LOCK = re.compile(r"flip a coin\. if tails, (?:during your next turn, )?this pokémon can't "
                       r"(?:attack|use attacks|use ([a-z' -]+?))(?: during your next turn)?\.")
SMOKE = re.compile(r"(?:during your opponent's next turn, )?if the defending pokémon tries to "
                   r"(?:use an )?attack(?: during your opponent's next turn)?, your opponent flips "
                   r"(a coin|2 coins)\. if (?:tails|either of them is tails), that attack "
                   r"(?:does nothing|doesn't happen)\.")
FLIP_PREVENT = re.compile(r"if any damage is done to this pokémon by attacks during your opponent's "
                          r"next turn, flip a coin\. if heads, prevent that damage\.")
ALL_HEADS_PROTECT = re.compile(r"flip (\d+) coins\..*if all of them are heads, .*prevent all "
                               r"(?:damage|effects of attacks, including damage)")


class SweepCoinNextTurn(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    def board(self, d, attack):
        t = Table(self)
        self._table = t
        me = neutral(t.put(d, P1, 'active'))
        neutral(t.put(self.filler, P1, 'bench'))
        opp = neutral(t.put(OPP_ATTACKER, P2, 'active'))
        neutral(t.put(self.filler, P2, 'bench'))
        pay_cost(t, me, attack)
        pay_cost(t, opp, next(a for a in fixtures.definition(OPP_ATTACKER).abilities
                              if isinstance(a, Attack) and a.title == OPP_ATTACK))
        return t, me, opp

    async def use(self, t, me, attack, seq):
        t.heads = sc.coins(seq)
        entry = t.attack_offer(me, attack.title)
        if entry is None:
            return False
        await t.do(entry)
        return True

    async def opp_hits(self, t, me, opp, heads):
        """Opponent's turn: Dialga attacks with all coins forced. Returns damage to `me`."""
        t.next_turn()
        t.heads = heads
        before = t.hp(me)
        entry = t.attack_offer(opp, OPP_ATTACK, pid=P2)
        if entry is None:
            return 0
        await t.do(entry, pid=P2)
        return before - (t.hp(me) if me in t.board.pokemon_in_play(P1) else 0)

    # -------------------------------------------------------------- checks
    async def self_lock(self, d, a, m):
        out = []
        for heads in (True, False):
            t, me, opp = self.board(d, a)
            if not await self.use(t, me, a, [heads]):
                return False, 'attack not offered'
            t.next_turn()
            t.next_turn()
            pay_cost(t, me, a)
            if m.group(1):
                titles = [x.title for x in d.abilities
                          if isinstance(x, Attack) and x.title.lower() == m.group(1)]
            else:
                titles = [x.title for x in d.abilities if isinstance(x, Attack)]
            free = [bool(t.attack_offer(me, title)) for title in titles]
            want = [heads] * len(titles)
            if m.group(1) is None and not heads:
                want = [False] * len(titles)
            if free != want:
                out.append(f"{'H' if heads else 'T'}: offered {dict(zip(titles, free))}")
        return not out, '; '.join(out)

    async def smoke(self, d, a, m):
        out = []
        coins = 1 if m.group(1) == 'a coin' else 2
        for opp_heads, want_hit in ((True, True), (False, False)):
            t, me, opp = self.board(d, a)
            if not await self.use(t, me, a, [True] * 3):
                return False, 'attack not offered'
            got = await self.opp_hits(t, me, opp, opp_heads)
            if bool(got) != want_hit:
                out.append(f"opp {'heads' if opp_heads else 'tails'}: took {got}")
        if coins == 2:      # one heads + one tails: still stopped
            t, me, opp = self.board(d, a)
            await self.use(t, me, a, [True] * 3)
            t.next_turn()
            t.heads = sc.coins([True, False])
            before = t.hp(me)
            entry = t.attack_offer(opp, OPP_ATTACK, pid=P2)
            if entry is not None:
                await t.do(entry, pid=P2)
            if before != t.hp(me):
                out.append("opp heads+tails: attack still hit")
        return not out, '; '.join(out)

    async def flip_prevent(self, d, a, m):
        out = []
        for heads, want in ((True, 0), (False, OPP_DAMAGE)):
            t, me, opp = self.board(d, a)
            if not await self.use(t, me, a, [True]):
                return False, 'attack not offered'
            got = await self.opp_hits(t, me, opp, heads)
            if got != want:
                out.append(f"{'H' if heads else 'T'}: took {got} want {want}")
        return not out, '; '.join(out)

    async def all_heads_protect(self, d, a, m):
        n = int(m.group(1))
        out = []
        for seq, want in (([True] * n, 0), ([True] * (n - 1) + [False], OPP_DAMAGE)):
            t, me, opp = self.board(d, a)
            if not await self.use(t, me, a, seq):
                return False, 'attack not offered'
            got = await self.opp_hits(t, me, opp, True)
            if got != want:
                out.append(f"{sum(seq)}H: took {got} want {want}")
        return not out, '; '.join(out)

    async def test_sweep(self):
        from unittest.mock import patch
        from spirit.game.session.game_session import GameSession

        def coins(session, player_id, count):
            h = self._table.heads
            return [bool(h('attack check') if callable(h) else h) for _ in range(count)]
        with patch.object(GameSession, '_attack_attempt_coins', coins):
            await self._sweep()

    async def _sweep(self):
        checks = [('self_lock', SELF_LOCK, self.self_lock), ('smokescreen', SMOKE, self.smoke),
                  ('flip_prevent', FLIP_PREVENT, self.flip_prevent),
                  ('all_heads_protect', ALL_HEADS_PROTECT, self.all_heads_protect)]
        report = {}
        for name, rx, fn in checks:
            checked, failures, errors = 0, [], []
            for d in unique_pokemon():
                if any(not isinstance(x, Attack) for x in d.abilities or []):
                    continue
                for a in d.abilities or []:
                    if not isinstance(a, Attack):
                        continue
                    m = rx.search(norm(a.game_text))
                    if not m:
                        continue
                    checked += 1
                    try:
                        ok, detail = await fn(d, a, m)
                    except Exception as ex:
                        errors.append({'card': label(d, a), 'error': f"{type(ex).__name__}: {ex}"})
                        continue
                    if not ok:
                        failures.append({'card': label(d, a), 'text': a.game_text, 'detail': detail})
            report[name] = {'checked': checked, 'failures': failures, 'errors': errors}
            print(f"{name}: checked {checked}, failures {len(failures)}, errors {len(errors)}")
            self.assertEqual([f['card'] for f in failures + errors], [], name)
        os.makedirs(REPORT_DIR, exist_ok=True)
        with open(os.path.join(REPORT_DIR, 'coin_next_turn.json'), 'w') as fh:
            json.dump(report, fh, indent=1, ensure_ascii=False)


if __name__ == "__main__":
    unittest.main()
