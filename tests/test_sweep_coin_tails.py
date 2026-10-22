"""Sweep: every "Flip a coin. If heads, <effect>." attack does NOTHING extra
on tails.

For each matching attack the attack is resolved twice on identical boards:
  * with its real text and the coin forced to tails;
  * with its text removed (printed damage only) -- the control.
The two resulting boards must match: zone sizes, every Pokémon's HP /
conditions / attachments, both Actives, and the turn's lock/effect
bookkeeping.  A difference means the heads-only effect happened on tails
(the Tapu Fini Dream Away report).

Also: on heads, *something* should differ from the control; when nothing does
the card is listed as "heads did nothing" (likely an unimplemented effect).
"""
import copy
import json
import os
import re
import unittest

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.sweep_core import std_board, unique_pokemon, norm, label, REPORT_DIR
from spirit.game.attributes import AttrID
from spirit.game.data_utils import Attack
from spirit.game.session.effects import EffectContext
from spirit.tools.effect_smoke import P1, P2

# Entire text is one heads clause (anything after it would also apply on tails).
PATTERN = re.compile(r"^flip a coin\. if heads, (?!.*\bif tails\b)[^.]*(?:\([^)]*\))?[^.]*\.$")

# turn_state bookkeeping that changes for any attack / any flip.
NOISE = {'attacks_used', 'coin_flips', 'coin_results', 'flips', 'last_coin_results',
         'damage_dealt_this_turn', 'attack_damage', 'actions_taken'}


def signature(t, b):
    board, state = t.board, t.state
    sig = {}
    for pid in (P1, P2):
        for zone in ('hand', 'deck', 'discard', 'prizes', 'bench'):
            sig[f'{pid}:{zone}'] = len(t.zone(pid, zone))
        active = board.active_pokemon(pid)
        sig[f'{pid}:active'] = getattr(active, 'archetype_id', None)
        for i, mon in enumerate(board.pokemon_in_play(pid)):
            sig[f'{pid}:mon{i}'] = (
                mon.archetype_id, mon.get_attribute(AttrID.HP, 0),
                tuple(sorted(mon.get_attribute(AttrID.SPECIAL_CONDITIONS) or [])),
                len(mon.children))
    for name, value in vars(state).items():
        if name in NOISE or name.startswith('_'):
            continue
        if isinstance(value, (dict, list, set, tuple)):
            sig[f'state.{name}'] = len(value)
        elif isinstance(value, (bool, int)) and name not in ('turn_number',):
            sig[f'state.{name}'] = value
    sig['temporary_passives'] = len(getattr(board, 'temporary_passives', None) or [])
    return sig


class SweepCoinTails(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    def _prep(self, b):
        """Give heads effects something to act on (same board for all runs)."""
        from spirit.game.attributes import PokemonTypes
        t = b.t
        t.energy(b.opp, PokemonTypes.WATER, 2)
        t.energy(b.opp_bench, PokemonTypes.FIRE)
        for _ in range(3):
            t.put(self.item, P2, 'hand')
        for kind in (PokemonTypes.FIRE, PokemonTypes.WATER, PokemonTypes.GRASS,
                     PokemonTypes.LIGHTNING, PokemonTypes.PSYCHIC):
            t.put(t.basic_energy(kind), P1, 'discard')
        t.put(self.filler, P1, 'discard')
        t.put(self.item, P1, 'discard')
        hp = b.me.get_attribute(AttrID.HP, 0)
        if hp > 40:
            b.me.set_attribute(AttrID.HP, hp - 30)
        b.my_bench.set_attribute(AttrID.HP, b.my_bench.get_attribute(AttrID.HP, 0) - 30)

    async def _resolve(self, d, attack, *, heads, strip_text):
        b = std_board(self, d, attack, heads=heads, prep=self._prep)
        used = attack
        if strip_text:
            used = copy.copy(attack)
            used.game_text = ""
            used.damage_operator = None
        ctx = EffectContext(b.t.session, P1, b.me, used)
        effect = used.effect
        if effect is None:
            return signature(b.t, b)
        await b.t._run(lambda: effect(ctx))
        return signature(b.t, b)

    async def test_sweep(self):
        checked, failures, heads_nothing, errors = 0, [], [], []
        for d in unique_pokemon():
            for a in getattr(d, 'abilities', None) or []:
                if not isinstance(a, Attack):
                    continue
                m = PATTERN.match(norm(a.game_text))
                if not m or "this attack does" in norm(a.game_text):
                    continue          # damage-setting clauses: see test_sweep_coins
                checked += 1
                try:
                    control = await self._resolve(d, a, heads=False, strip_text=True)
                    tails = await self._resolve(d, a, heads=False, strip_text=False)
                    heads = await self._resolve(d, a, heads=True, strip_text=False)
                except Exception as ex:
                    errors.append({'card': label(d, a), 'error': f"{type(ex).__name__}: {ex}"})
                    continue
                diff = {k: (control.get(k), tails.get(k)) for k in set(control) | set(tails)
                        if control.get(k) != tails.get(k)}
                if diff:
                    failures.append({'card': label(d, a), 'text': a.game_text,
                                     'tails_changed': {k: list(v) for k, v in diff.items()}})
                elif heads == control:
                    heads_nothing.append({'card': label(d, a), 'text': a.game_text})
        os.makedirs(REPORT_DIR, exist_ok=True)
        with open(os.path.join(REPORT_DIR, 'coin_tails.json'), 'w') as fh:
            json.dump({'checked': checked, 'tails_did_something': failures,
                       'heads_did_nothing': heads_nothing, 'errors': errors},
                      fh, indent=1, ensure_ascii=False)
        print(f"coin_tails: checked {checked}, tails wrong {len(failures)}, "
              f"heads did nothing {len(heads_nothing)}, errors {len(errors)}")
        self.assertEqual([f['card'] for f in failures], [])
        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
