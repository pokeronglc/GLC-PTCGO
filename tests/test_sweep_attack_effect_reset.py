"""Sweep: an ATTACK's effect on a Pokémon ends when that Pokémon changes.

OWNER RULE (Oct 12): any effect an attack puts on a Pokémon -- on the
attacker itself ("during your next turn, this Pokémon's X does N more
damage", "prevent all damage done to this Pokémon during your opponent's
next turn", "this Pokémon can't attack / retreat during your next turn",
"takes N less damage") or on the Defending Pokémon ("can't attack / retreat",
"its attacks do N less damage", "can't be healed", Smokescreen checks,
delayed Knock Outs, attach restrictions ...) ends when that Pokémon evolves,
devolves, goes to the hand / deck / discard pile (KO or otherwise) / Lost
Zone, or moves from the Active Spot to the Bench.  Damage counters stay on
evolve / devolve / bench.  Ability / Trainer / Tool / Stadium effects are
not attack effects and are not ended by this rule.

How the sweep proves it, for every distinct GLC attack text that creates a
"next turn" effect (one printing per text and implementation -- a reprint
with its own script is tested separately from the shared interpreter):

  * two boards are built -- EFFECT (the attack is used) and BASELINE (it is
    not; a self/gust switch the attack makes is mirrored);
  * for each Active Pokémon the attack could have marked (P1 = the attacker,
    P2 = the Defending Pokémon) and each transition (none, evolve, devolve,
    to hand, to deck, to discard, Knocked Out, Lost Zone, Active -> Bench via
    switch) the transition is applied to that Pokémon on both boards, the
    resulting Pokémon is put back into the Active Spot, the other side's
    Active is replaced by a fresh Pokémon, and a behaviour vector is read
    through the real rules: attacks / retreat / energy attachment offered,
    attack and retreat costs, damage dealt and taken (compute_damage),
    whether it must flip to attack, whether it can be healed, what a real
    opposing attack and a real energy attachment do to it, and what the
    Pokémon Checkup does to it;
  * CONTROL (no transition): the EFFECT vector must differ from BASELINE,
    or the Pokémon must carry an attack-sourced record (fingerprint) -- this
    proves the effect is live on that Pokémon;
  * every transition: EFFECT vector == BASELINE vector, and no attack-sourced
    record is left keyed to any card of that Pokémon.

Player-wide effects ("your opponent can't play Item cards", "whenever they
flip a coin") are not effects on a Pokémon and are counted as skipped.

Report: /home/claude/bughunt/sweep/attack_effect_reset.json
"""
import json
import os
import re
import unittest
from unittest.mock import patch

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table
from tests.sweep_core import unique_pokemon, norm, label, pay_cost, neutral, REPORT_DIR
from spirit.game.attributes import AttrID, PokemonStage, PokemonTypes
from spirit.game.data_utils import (
    ABILITIES_BY_ID, Attack, CARD_DEFS_BY_GUID, PokemonCardDef, def_for, has_rule_box,
    is_pokemon_ex,
)
from spirit.game.models.board import PokemonEntity
from spirit.game.session.effects import EffectContext, full_stack
from spirit.game.session.game_session import GameSession
from spirit.game.session.passives import (
    compute_damage, effective_attack_cost, effective_retreat_cost, healing_blocked,
)
from spirit.tools.effect_smoke import P1, P2, _def_attr

BIG = 999
SELECT = re.compile(r"next turn|can't be healed|until this [a-z' -]+ leaves the active spot")
PLAYER_WIDE = re.compile(
    r"can't play any|can't play pokémon|can't be played from your opponent's hand|"
    r"can't play any pokémon|whenever (they|your opponent) (flip|plays|try)|"
    r"they flip a coin|treat it as tails|each player|your pokémon can't attack|"
    r"pokémon that have 2 or less energy|each pokémon your opponent has|"
    r"each stadium or pokémon tool|any number of energy cards|"
    r"can't draw a card|ignore all energy in the attack costs of|"
    r"to evolve (his or her|their) pokémon|each of your future pokémon|"
    r"whenever they try to use a trainer")
# Report families (first match wins).
FAMILIES = [
    ('delayed_ko_or_counters', r"at the end of your opponent's next turn|is knocked out at the end"),
    ('smokescreen', r"tries to (use an )?attack"),
    ('cant_attack', r"can't attack|can't use attacks|can't use [a-z' -]+ during|can't use that attack|can only use that attack"),
    ('cant_retreat_or_cost', r"can't retreat|retreat cost|has no retreat cost|cost colorless"),
    ('prevent_or_reduce_taken', r"prevent|less damage from attacks|is reduced by \d+ \(after|not knocked out|can't take any prize"),
    ('more_damage_taken', r"takes \d+ more damage|is increased by|it will be knocked out|it is knocked out|weakness"),
    ('less_damage_dealt', r"less damage|damage done by attacks? from the defending pokémon is reduced"),
    ('more_damage_dealt', r"more damage|base damage is|instead of|coins instead"),
    ('attach_or_heal', r"energy|healed"),
    ('other', r"."),
]
TRANSITIONS = ('evolve', 'devolve', 'hand', 'deck', 'discard', 'ko', 'lostzone', 'bench')
# Vanilla Defending Pokémon: Shelmet (evolves into vanilla Accelgor) and,
# for devolve / "Evolution Pokémon" / "choose 1 of its attacks" texts,
# vanilla two-attack Diggersby with vanilla Bunnelby underneath.
DEFENDER = 'SWSH3.Shelmet_9'
DEFENDER_STAGE1, DEFENDER_UNDER = 'SWSH3.Diggersby_96', 'SM4.Bunnelby_87'
STADIUM, SPECIAL_ENERGY = 'SWSH2.TrainingCourt_169', 'XY1.RainbowEnergy_131'
# Conditions a GLC board can never meet, or riders no behaviour reading sees.
NOT_TESTABLE = {
    "is a pokémon v, it can't attack": 'no Pokémon V in GLC',
    "is a pokémon-ex, that pokémon can't attack": 'no Pokémon-EX in GLC',
    "flip 6 coins instead of 2": 'coin count of a later attack (no board reading)',
}


def defender_variant(text, role, kind):
    if kind == 'evolve' and "evolution pokémon, it can't attack" not in text:
        return 'basic'
    if (role == P2 and kind == 'devolve') or "evolution pokémon, it can't attack" in text \
            or "choose 1 of the defending pokémon's attack" in text \
            or "choose 1 of your opponent's active pokémon's attacks" in text:
        return 'stage1'
    return 'basic'


def family(text):
    return next(name for name, rx in FAMILIES if re.search(rx, text))


def _vanilla(d):
    return (not has_rule_box(d.guid)
            and all(isinstance(a, Attack) and a.effect is None and a.passive is None
                    and not a.trigger for a in d.abilities))


_EVOS = None


def _evolutions():
    """EVOLUTION_LOGIC_NAME -> [evolution defs], vanilla first."""
    global _EVOS
    if _EVOS is None:
        _EVOS = {}
        for d in CARD_DEFS_BY_GUID.values():
            if isinstance(d, PokemonCardDef):
                frm = _def_attr(d, AttrID.EVOLUTION_LOGIC_FROM)
                if frm and _def_attr(d, AttrID.STAGE) in (
                        PokemonStage.STAGE1.value, PokemonStage.STAGE2.value):
                    _EVOS.setdefault(frm, []).append(d)
        for name in _EVOS:
            _EVOS[name].sort(key=lambda d: (not _vanilla(d), d.guid))
    return _EVOS


_PREVS = None


def _pre_evolution(d):
    """A Basic / Stage 1 def `d` evolves from, vanilla first (or None)."""
    global _PREVS
    if _PREVS is None:
        _PREVS = {}
        for x in CARD_DEFS_BY_GUID.values():
            if isinstance(x, PokemonCardDef):
                _PREVS.setdefault(_def_attr(x, AttrID.EVOLUTION_LOGIC_NAME), []).append(x)
        for name in _PREVS:
            _PREVS[name].sort(key=lambda x: (not _vanilla(x), x.guid))
    frm = _def_attr(d, AttrID.EVOLUTION_LOGIC_FROM)
    options = _PREVS.get(frm) if frm else None
    return options[0] if options else None


def fingerprint(session, ids):
    """Live attack-sourced records keyed to any of `ids`."""
    st = session.turn_state
    turn = st.turn_number

    def live(exp, default=True):
        return getattr(exp, 'from_attack', default) and exp >= turn

    out = []
    for (eid, aid), exp in st.attack_locks.items():
        if eid in ids and live(exp):
            out.append(('attack_lock', aid))
    for name in ('retreat_locks', 'attach_restrictions'):
        for eid, exp in getattr(st, name).items():
            if eid in ids and live(exp):
                out.append((name, eid))
    for name in ('attack_flip_checks', 'attach_ends_turn_checks'):
        for eid, entry in getattr(st, name).items():
            if eid in ids and live(entry[0]):
                out.append((name, eid))
    for mod in st.damage_modifiers:
        if getattr(mod, 'source_entity_id', None) in ids and getattr(mod, 'from_attack', False) \
                and (mod.expires_after_turn is None or mod.expires_after_turn >= turn):
            out.append(('damage_modifier', mod.amount))
    for tp in session.board_state.temporary_passives:
        if tp.carrier_entity_id in ids and tp.player_id is None and tp.from_attack \
                and (tp.expires_after_turn is None or tp.expires_after_turn >= turn):
            out.append(('temp_passive', type(tp.passive).__name__))
    for entry in getattr(session, 'scheduled_effects', []):
        if entry.get('entity_id') in ids and entry.get('from_attack', True):
            out.append(('scheduled', entry.get('fire_at_checkup_of_turn')))
    return out


def stack_ids(pokemon):
    return {c.entity_id for c in full_stack(pokemon) if isinstance(c, PokemonEntity)}


class Scenario:
    """One board: optional attack, optional transition on one role, measure."""

    def __init__(self, test, d, attack, *, heads, use_attack, defender):
        self.test, self.d, self.attack = test, d, attack
        self.heads, self.use_attack, self.defender_spec = heads, use_attack, defender
        self.text = norm(attack.game_text)

    def build(self):
        test = self.test
        t = self.t = Table(test)
        t.heads = self.heads
        me = t.put(self.d, P1, 'active')
        prev = _pre_evolution(self.d)
        if prev is not None and _def_attr(self.d, AttrID.STAGE) in (
                PokemonStage.STAGE1.value, PokemonStage.STAGE2.value):
            under = t.put(prev, P1, 'hand')
            t.board.attach_card(under.entity_id, me.entity_id)
        neutral(me)
        neutral(t.put(test.filler, P1, 'bench'))
        if self.defender_spec == 'stage1':
            opp = t.put(DEFENDER_STAGE1, P2, 'active')
            under = t.put(DEFENDER_UNDER, P2, 'hand')
            t.board.attach_card(under.entity_id, opp.entity_id)
        else:
            opp = t.put(DEFENDER, P2, 'active')
        neutral(opp)
        # Satisfy the attack's own condition on BOTH boards.
        text = self.text
        if "darkness or fairy pokémon" in text:
            opp.set_attribute(AttrID.POKEMON_TYPES, [PokemonTypes.DARKNESS.value])
        if "has a stadium" in text:
            t.stadium(STADIUM, P2)
        if "discard a special energy attached to your opponent's active" in text:
            t.attach(SPECIAL_ENERGY, opp)
        if "knocked out by damage from this attack" in text:
            opp.set_attribute(AttrID.HP, 10)
        neutral(t.put(test.filler, P2, 'bench'))
        for pid in (P1, P2):
            for _ in range(2):
                t.put(t.basic_energy(PokemonTypes.WATER), pid, 'hand')
        pay_cost(t, me, self.attack)
        self.attacker, self.opp = me, opp

    async def act(self):
        """Use the attack (EFFECT) or mirror its board movement (BASELINE)."""
        t = self.t
        if self.use_attack:
            entry = t.attack_offer(self.attacker, self.attack.title)
            if entry is None:
                return False
            if 'rock-paper-scissors' in self.text:
                # Tricky Slap: we play Rock (first button); make them Scissors.
                with patch('random.sample', lambda seq, k: ['Scissors', 'Rock', 'Paper']):
                    await t.do(entry)
                return True
            await t.do(entry)
            return True
        if t.attack_offer(self.attacker, self.attack.title) is None:
            return False
        if "switch this pokémon with 1 of your benched" in self.text:
            self._raw_swap(P1)
        if "switch 1 of your opponent's benched pokémon with" in self.text:
            self._raw_swap(P2)
        # What the attack discards / Knocks Out goes on the BASELINE too.
        board = t.board
        if "has a stadium" in self.text:
            for card in list(board.find_global_area('activeStadium').children):
                board.move_card(card.entity_id, self._area(P2, 'discard').entity_id)
        if "discard a special energy attached to your opponent's active" in self.text:
            for card in list(self.opp.children):
                if card.get_attribute(AttrID.IS_SPECIAL_ENERGY):
                    board.move_card(card.entity_id, self._area(P2, 'discard').entity_id)
        if "knocked out by damage from this attack" in self.text:
            board.move_card(self.opp.entity_id, self._area(P2, 'discard').entity_id)
            self._raw_make_active(next(c for c in self._area(P2, 'bench').children
                                       if isinstance(c, PokemonEntity)))
        return True

    # -- board plumbing (no rules run: nothing is cleared) ----------------
    def _area(self, pid, name):
        return self.t.board.find_player_area(pid, name)

    def _raw_swap(self, pid):
        board = self.t.board
        active = board.active_pokemon(pid)
        bench = [c for c in self._area(pid, 'bench').children if isinstance(c, PokemonEntity)]
        if active is None or not bench:
            return
        board.move_card(active.entity_id, self._area(pid, 'bench').entity_id)
        board.move_card(bench[0].entity_id, self._area(pid, 'activePokemonArea').entity_id)

    def _raw_make_active(self, pokemon):
        board = self.t.board
        pid = pokemon.owning_player_id
        current = board.active_pokemon(pid)
        if current is pokemon:
            return
        if current is not None:
            board.move_card(current.entity_id, self._area(pid, 'bench').entity_id)
        board.move_card(pokemon.entity_id, self._area(pid, 'activePokemonArea').entity_id)

    def _fresh_other_side(self, pid):
        """Bench the other side's Active (raw) and promote its fresh filler."""
        board = self.t.board
        active = board.active_pokemon(pid)
        bench = [c for c in self._area(pid, 'bench').children
                 if isinstance(c, PokemonEntity) and c is not active]
        filler = next((c for c in bench if not fingerprint(self.t.session, stack_ids(c))), None)
        if filler is None:
            filler = self.t.put(self.test.filler, pid, 'bench')
        self._raw_make_active(filler)

    def _equalize(self, pokemon):
        t = self.t
        neutral(pokemon)
        t.state.entered_play_turn[pokemon.entity_id] = 0
        definition = def_for(pokemon.archetype_id)
        for attack in getattr(definition, 'abilities', None) or []:
            if isinstance(attack, Attack):
                pay_cost(t, pokemon, attack)
        t.energy(pokemon, PokemonTypes.COLORLESS if PokemonTypes.COLORLESS.value in t.test.energies
                 else PokemonTypes.WATER, 4)

    # -- transitions -----------------------------------------------------
    async def transition(self, x, kind):
        """Apply `kind` to Pokémon `x`; returns the Pokémon that now stands
        for it (back in the Active Spot), or a skip reason string."""
        t = self.t
        owner = x.owning_player_id
        ctx = EffectContext(t.session, owner, x, None)
        if kind == 'evolve':
            options = _evolutions().get(x.get_attribute(AttrID.EVOLUTION_LOGIC_NAME)) or []
            if not options:
                return 'no evolution in pool'
            card = t.put(options[0], owner, 'hand')
            ok = await t._run(lambda: t.session.perform_evolution(owner, card, x))
            if not ok:
                return 'evolution prevented'
            new = card
        elif kind == 'devolve':
            frm = x.get_attribute(AttrID.EVOLUTION_LOGIC_FROM)
            if not any(isinstance(c, PokemonEntity)
                       and c.get_attribute(AttrID.EVOLUTION_LOGIC_NAME) == frm for c in x.children):
                return 'not an evolved Pokémon'
            await t._run(lambda: ctx.devolve_pokemon(x, 1, 'hand'))
            new = t.board.active_pokemon(owner)
            if new is x or new is None:
                return 'devolve prevented'
        elif kind == 'bench':
            bench = [c for c in self._area(owner, 'bench').children if isinstance(c, PokemonEntity)]
            if not await t._run(lambda: ctx.switch_active(owner, bench[0])):
                return 'switch prevented'
            new = x
        else:
            if kind == 'hand':
                await t._run(lambda: ctx.put_in_hand([x]))
            elif kind == 'deck':
                await t._run(lambda: ctx.shuffle_into_deck([x], owner))
            elif kind == 'discard':
                await t._run(lambda: ctx.discard_cards([x]))
            elif kind == 'lostzone':
                await t._run(lambda: ctx.move_to_lost_zone([x]))
            elif kind == 'ko':
                await t._run(lambda: ctx.knock_out(x))
                await t.knockouts(ctx)
            if x in t.board.pokemon_in_play(owner):
                return f'{kind} prevented'
            # Replayed: the same card (entity) comes back as a new Pokémon.
            new = x
        self._raw_make_active(new)
        new.set_attribute(AttrID.HP, BIG)
        return new

    # -- measuring -------------------------------------------------------
    def _offers(self, pokemon, pid):
        titles = set()
        for e in self.t.offers(pokemon, 'UsePokemonAttack', pid):
            ab = ABILITIES_BY_ID.get(e['selectableAction']['actionID'])
            if ab is not None and 'during your last turn' not in norm(ab.game_text):
                titles.add(ab.title)
        return tuple(sorted(titles))

    def _attach_target(self, pokemon, pid):
        t = self.t
        card = next((c for c in t.zone(pid, 'hand')
                     if t.offers(c, 'DefaultEnergyPlayAbility', pid)), None)
        if card is None:
            return None, None
        return card, pokemon.entity_id in t.targets(card, 'DefaultEnergyPlayAbility', pid)

    def _static(self, x, other, pid):
        t, board = self.t, self.t.board
        definition = def_for(x.archetype_id)
        attacks = [a for a in (getattr(definition, 'abilities', None) or []) if isinstance(a, Attack)]
        dealt = tuple((a.title, compute_damage(board, x, other, 100, attack_title=a.title).amount)
                      for a in attacks)
        taken = compute_damage(board, other, x, 100)
        costs = []
        for entry in x.get_attribute(AttrID.PIE_ABILITIES) or []:
            if isinstance(entry, dict) and entry.get('abilityType') == 'Attack':
                ab = ABILITIES_BY_ID.get(entry.get('abilityID'))
                cost = effective_attack_cost(board, x, dict(entry.get('cost') or {}), attack=ab)
                costs.append((getattr(ab, 'title', '?'),
                              tuple(sorted((str(k), v) for k, v in cost.items()))))
        return {
            'retreat_cost': effective_retreat_cost(board, x),
            'costs': tuple(costs),
            'dealt': dealt,
            'taken': (taken.amount, taken.prevented),
            'flip': t.state.attack_flip_check(x.entity_id) is not None,
            'heal_blocked': healing_blocked(board, x),
        }

    async def measure(self, x):
        """Behaviour vector of `x` (already Active, other side fresh)."""
        t, board = self.t, self.t.board
        pid = x.owning_player_id
        other_pid = P2 if pid == P1 else P1
        v = {}
        for pokemon in board.pokemon_in_play(P1) + board.pokemon_in_play(P2):
            pokemon.set_attribute(AttrID.HP, BIG)
        self._equalize(x)
        self._equalize(board.active_pokemon(other_pid))
        t.heads = False
        # -- window 1: the opponent's (P2's) next turn ------------------
        t.next_turn()
        p2a, p1a = board.active_pokemon(P2), board.active_pokemon(P1)
        side = (p2a, p1a) if pid == P2 else (p1a, p2a)
        v['w1'] = self._static(side[0], side[1], pid)
        if pid == P2:
            v['w1']['offers'] = self._offers(p2a, P2)
            v['w1']['retreat'] = t.can(p2a, 'BaseRetreat', P2)
            card, ok = self._attach_target(p2a, P2)
            v['w1']['attach'] = ok
            if card is not None and ok:
                entry = next(iter(t.offers(card, 'DefaultEnergyPlayAbility', P2)))
                before = t.hp(p2a)
                ends = await t._run(lambda: t.session._execute_attach_energy(
                    P2, card, entry, [p2a.entity_id]))
                v['w1']['attach_result'] = (bool(ends), before - t.hp(p2a),
                                            tuple(sorted(t.conditions(p2a))))
        # a real attack by P2's Active on P1's Active
        title = next(iter(self._offers(p2a, P2)), None)
        hp1, hp2 = t.hp(p1a), t.hp(p2a)
        if title is not None:
            await t.do(t.attack_offer(p2a, title, pid=P2), pid=P2)
        v['w1']['p2_attack'] = (
            title is not None,
            (hp1 - t.hp(p1a)) if p1a in board.pokemon_in_play(P1) else 'KO',
            (hp2 - t.hp(p2a)) if p2a in board.pokemon_in_play(P2) else 'KO')
        # end of P2's turn: Pokémon Checkup (delayed Knock Outs / counters)
        hpx = t.hp(x)
        await t.checkup()
        v['checkup'] = ((hpx - t.hp(x)) if x in board.pokemon_in_play(pid) else 'gone')
        # -- window 2: the attacker's (P1's) next turn -------------------
        t.next_turn()
        p2a, p1a = board.active_pokemon(P2), board.active_pokemon(P1)
        if p1a is None or p2a is None:
            v['w2'] = 'no active'
            return v
        side = (p2a, p1a) if pid == P2 else (p1a, p2a)
        v['w2'] = self._static(side[0], side[1], pid)
        if pid == P1:
            v['w2']['offers'] = self._offers(p1a, P1)
            v['w2']['retreat'] = t.can(p1a, 'BaseRetreat', P1)
            v['w2']['attach'] = self._attach_target(p1a, P1)[1]
        return v


class SweepAttackEffectReset(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    async def asyncSetUp(self):
        import asyncio
        asyncio.get_running_loop().set_debug(False)   # 3x faster sweep

    async def run_role(self, d, a, heads, role, kind):
        """(effect_vec, baseline_vec, fp_after_attack, fp_after, status)."""
        defender = defender_variant(norm(a.game_text), role, kind)
        out = []
        fp_attack = fp_after = None
        for use_attack in (True, False):
            sc = Scenario(self, d, a, heads=heads, use_attack=use_attack, defender=defender)
            sc.build()
            if not await sc.act():
                return None, None, None, None, 'attack not offered'
            t = sc.t
            x = t.board.active_pokemon(role)
            if x is None:
                return None, None, None, None, 'no Active'
            if use_attack:
                fp_attack = fingerprint(t.session, stack_ids(x))
            old_ids = stack_ids(x)
            if kind is not None:
                new = await sc.transition(x, kind)
                if isinstance(new, str):
                    return None, None, fp_attack, None, new
                x = new
                if use_attack:
                    fp_after = fingerprint(t.session, old_ids | stack_ids(x) | {x.entity_id})
            sc._fresh_other_side(P2 if role == P1 else P1)
            out.append(await sc.measure(x))
        return out[0], out[1], fp_attack, fp_after, 'ok'

    async def check_group(self, d, a):
        text = norm(a.game_text)
        heads = not re.search(r"if tails, (during your (opponent's )?next turn, )?"
                              r"(this pokémon|any damage)", text)
        result = {'card': label(d, a), 'text': a.game_text, 'family': family(text),
                  'roles': {}, 'failures': []}
        for role in (P1, P2):
            eff, base, fp, _, status = await self.run_role(d, a, heads, role, None)
            if status != 'ok':
                result['skip'] = status
                return result
            observed = []
            if eff != base:
                observed.append('behaviour')
            if fp:
                observed.append('fingerprint')
            if not observed:
                continue
            role_name = 'attacker' if role == P1 else 'defender'
            role_out = result['roles'][role_name] = {'observed': observed, 'transitions': {}}
            for kind in TRANSITIONS:
                eff_t, base_t, _, fp_t, status = await self.run_role(d, a, heads, role, kind)
                if status != 'ok':
                    role_out['transitions'][kind] = status
                    continue
                problems = []
                if eff_t != base_t:
                    diff = {k: (eff_t.get(k), base_t.get(k)) for k in eff_t
                            if eff_t.get(k) != base_t.get(k)}
                    problems.append(f"behaviour differs: {diff}")
                if fp_t:
                    problems.append(f"records left: {fp_t}")
                role_out['transitions'][kind] = 'ok' if not problems else 'FAIL'
                if problems:
                    result['failures'].append(
                        f"{'attacker' if role == P1 else 'defender'} {kind}: " + '; '.join(problems))
        return result

    async def test_sweep(self):
        def tails(session, player_id, count):
            return [False] * count
        with patch.object(GameSession, '_attack_attempt_coins', tails):
            await self._sweep()

    async def _sweep(self):
        # One printing per (text, implementation): reprints that share the
        # interpreter count once, a card with its own script counts again.
        groups = {}
        for d in unique_pokemon():
            for a in d.abilities or []:
                if isinstance(a, Attack) and SELECT.search(norm(a.game_text)):
                    impl = (getattr(a.effect, '__module__', None),
                            getattr(a.effect, '__qualname__', None))
                    groups.setdefault((norm(a.game_text), impl), (d, a))
        limit = int(os.environ.get('SWEEP_LIMIT', '0') or 0)
        only = os.environ.get('SWEEP_ONLY')
        report, per_family = [], {}
        for (text, _impl), (d, a) in sorted(groups.items(), key=lambda kv: (kv[0][0], str(kv[0][1]))):
            if only and only.lower() not in text and only.lower() not in label(d, a).lower():
                continue
            if limit and len(report) >= limit:
                break
            fam = per_family.setdefault(family(text), {
                'groups': 0, 'player_wide': 0, 'skipped': 0, 'unobserved': 0,
                'observed': 0, 'transitions_checked': 0, 'transitions_skipped': 0,
                'failures': 0})
            fam['groups'] += 1
            untestable = next((why for key, why in NOT_TESTABLE.items() if key in text), None)
            if untestable:
                fam['skipped'] += 1
                report.append({'card': label(d, a), 'text': a.game_text, 'skip': untestable})
                continue
            if PLAYER_WIDE.search(text):
                fam['player_wide'] += 1
                report.append({'card': label(d, a), 'text': a.game_text, 'skip': 'player-wide'})
                continue
            try:
                res = await self.check_group(d, a)
            except Exception as ex:  # a crash is a finding
                res = {'card': label(d, a), 'text': a.game_text, 'roles': {},
                       'failures': [f"ERROR {type(ex).__name__}: {ex}"]}
            report.append(res)
            if res.get('skip'):
                fam['skipped'] += 1
                continue
            if not res['roles'] and not res['failures']:
                fam['unobserved'] += 1
                continue
            fam['observed'] += 1
            for role in res['roles'].values():
                for status in role['transitions'].values():
                    if status in ('ok', 'FAIL'):
                        fam['transitions_checked'] += 1
                    else:
                        fam['transitions_skipped'] += 1
            fam['failures'] += bool(res['failures'])
        os.makedirs(REPORT_DIR, exist_ok=True)
        name = os.environ.get('SWEEP_REPORT', 'attack_effect_reset')
        with open(os.path.join(REPORT_DIR, f'{name}.json'), 'w') as fh:
            json.dump({'families': per_family, 'groups': report}, fh, indent=1,
                      ensure_ascii=False, default=str)
        for name, fam in sorted(per_family.items()):
            print(f"{name}: {fam}")
        failures = [f"{r['card']}: {r['failures']}" for r in report if r.get('failures')]
        self.assertEqual(failures, [])
        # CONTROL: every Pokémon-tied effect must be live on the standard
        # board (an empty list here means no attack text silently does nothing).
        unobserved = [r['card'] for r in report
                      if not r.get('skip') and not r.get('roles') and not r.get('failures')]
        self.assertEqual(unobserved, [], 'attack effect never observed (unimplemented?)')



class AttackEffectResetControls(unittest.IsolatedAsyncioTestCase):
    """Targeted checks next to the sweep: the Ancient-Ruins-style evolve
    path, and NON-attack effects that the owner rule must leave alone."""
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    def board(self, mine):
        t = Table(self)
        me = neutral(t.put(mine, P1, 'active'))
        bench = neutral(t.put(self.filler, P1, 'bench'))
        opp = neutral(t.put(self.filler, P2, 'active'))
        neutral(t.put(self.filler, P2, 'bench'))
        return t, me, bench, opp

    async def bench_and_back(self, t, me, bench):
        ctx = EffectContext(t.session, P1, me, None)
        await t._run(lambda: ctx.switch_active(P1, bench))
        self.assertIs(t.active(P1), bench)
        await t._run(lambda: ctx.switch_active(P1, me))
        self.assertIs(t.active(P1), me)

    async def test_ability_damage_boost_survives_active_to_bench(self):
        # Feraligatr TWM 41 Torrential Heart: "during this turn, attacks used
        # by this Pokémon do 120 more damage" -- an Ability, not an attack.
        t, me, bench, opp = self.board('SV05.Feraligatr_41')
        me.set_attribute(AttrID.HP, BIG)
        await t.use(me, 'Torrential Heart')
        self.assertEqual(compute_damage(t.board, me, opp, 100).amount, 220)
        await self.bench_and_back(t, me, bench)
        self.assertEqual(compute_damage(t.board, me, opp, 100).amount, 220)

    async def test_ability_protection_survives_active_to_bench_not_leaving_play(self):
        # Pupitar SM8 116 Hard Shell Evolution (Ability): prevent all damage
        # done to this Pokémon by the opponent's attacks until the end of
        # their next turn.
        t, me, bench, opp = self.board('SM8.Pupitar_116')
        await t.effect('SM8.Pupitar_116', me, 'Hard Shell Evolution')
        self.assertTrue(compute_damage(t.board, opp, me, 100).prevented)
        await self.bench_and_back(t, me, bench)
        self.assertTrue(compute_damage(t.board, opp, me, 100).prevented,
                        'an Ability effect must survive Active -> Bench')
        t.next_turn()
        self.assertTrue(compute_damage(t.board, opp, me, 100).prevented)
        # Leaving play makes it a new card: the effect is gone on replay.
        ctx = EffectContext(t.session, P1, me, None)
        await t._run(lambda: ctx.put_in_hand([me]))
        t.board.move_card(bench.entity_id, t.board.find_player_area(P1, 'bench').entity_id)
        t.board.move_card(me.entity_id, t.board.find_player_area(P1, 'activePokemonArea').entity_id)
        self.assertFalse(compute_damage(t.board, opp, me, 100).prevented)

    async def test_trainer_protection_survives_active_to_bench(self):
        # Acerola's Mischief (Supporter): prevent all damage from attacks by
        # the opponent's Pokémon ex done to the chosen Pokémon.
        # GLC has no Pokémon ex: stand the opposing filler in for one.
        t, me, bench, _ = self.board(self.filler)
        attacker = neutral(t.put(self.filler, P2, 'bench'))
        patcher = patch('spirit.game.scripts.cards.ME1.AcerolasMischief_113.is_pokemon_ex',
                        lambda archetype_id: archetype_id == attacker.archetype_id)
        patcher.start()
        self.addCleanup(patcher.stop)
        await t.effect('ME1.AcerolasMischief_113', None, pid=P1)
        self.assertTrue(compute_damage(t.board, attacker, me, 100).prevented)
        await self.bench_and_back(t, me, bench)
        self.assertTrue(compute_damage(t.board, attacker, me, 100).prevented,
                        'a Trainer effect must survive Active -> Bench')

    async def test_tool_survives_active_to_bench(self):
        # Hard Charm (Tool): the holder takes 20 less damage from attacks.
        t, me, bench, opp = self.board(self.filler)
        t.attach('XY1.HardCharm_119', me)
        self.assertEqual(compute_damage(t.board, opp, me, 100).amount, 80)
        await self.bench_and_back(t, me, bench)
        self.assertEqual(compute_damage(t.board, opp, me, 100).amount, 80)

    async def test_attack_shield_ends_on_active_to_bench(self):
        # The attack counterpart of the Pupitar control: Withdraw-style
        # "prevent all damage ... during your opponent's next turn".
        t, me, bench, opp = self.board(self.filler)
        attack = next(a for a in fixtures.definition('BW3.Dwebble_6').abilities
                      if isinstance(a, Attack) and a.title == 'Withdraw')
        ctx = EffectContext(t.session, P1, me, attack)
        from spirit.game.card_effects.passives_common import apply_protection
        await apply_protection(ctx, target=me, prevent=True)
        self.assertTrue(compute_damage(t.board, opp, me, 100).prevented)
        await self.bench_and_back(t, me, bench)
        self.assertFalse(compute_damage(t.board, opp, me, 100).prevented)

    async def test_conditions_kept_on_evolution_still_end_attack_effects(self):
        # Sea of Nothingness: Special Conditions survive evolve / devolve, so
        # perform_evolution skips clear_pokemon_effects -- every attack effect
        # must still end (end_attack_effects_on), and none may come back
        # when the evolution is peeled off again.
        t = Table(self)
        me = neutral(t.put(self.filler, P1, 'active'))
        neutral(t.put(self.filler, P1, 'bench'))
        opp = neutral(t.put(DEFENDER, P2, 'active'))
        neutral(t.put(self.filler, P2, 'bench'))
        t.stadium('SM4.SeaofNothingness_99', P1)
        attack = next(a for a in fixtures.definition('BW1.Galvantula_46').abilities
                      if isinstance(a, Attack) and a.title == 'Electroweb')
        ctx = EffectContext(t.session, P1, me, attack)
        from spirit.game.card_effects.passives_common import AttackDebuffPassive
        ctx.lock_retreat(opp)
        ctx.restrict_attachments(opp)
        ctx.require_attack_flip(opp)
        ctx.end_turn_if_energy_attached_to(opp)
        ctx.add_passive_through_opponents_turn(opp, AttackDebuffPassive(30))
        t.state.attack_locks[(opp.entity_id, 'raw-script-lock')] = t.state.turn_number + 1
        opp.set_attribute(AttrID.SPECIAL_CONDITIONS, ['Confused'])
        self.assertTrue(fingerprint(t.session, {opp.entity_id}))
        evo = t.put('SWSH3.Accelgor_10', P2, 'hand')
        self.assertTrue(await t._run(lambda: t.session.perform_evolution(P2, evo, opp)))
        self.assertEqual(t.conditions(evo), {'Confused'}, 'Sea of Nothingness keeps it')
        self.assertEqual(fingerprint(t.session, {opp.entity_id, evo.entity_id}), [])
        dctx = EffectContext(t.session, P2, evo, None)
        await t._run(lambda: dctx.devolve_pokemon(evo, 1, 'hand'))
        self.assertIs(t.active(P2), opp)
        self.assertEqual(fingerprint(t.session, {opp.entity_id, evo.entity_id}), [])
        self.assertFalse(t.state.retreat_locked(opp.entity_id))
        self.assertFalse(t.state.attach_restricted(opp.entity_id))
        self.assertIsNone(t.state.attack_flip_check(opp.entity_id))

    async def test_delayed_knock_out_ends_on_bench_and_back(self):
        # Grapploct SV045 52 Slow-Acting Syncope: the guard used to look only
        # at "is that entity Active at the Checkup", so a Switch + Switch
        # back (or a replay) still Knocked it Out.
        t = Table(self)
        me = t.put('SV045.Grapploct_52', P1, 'active')
        neutral(t.put(self.filler, P1, 'bench'))
        opp = neutral(t.put(DEFENDER, P2, 'active'))
        bench = neutral(t.put(self.filler, P2, 'bench'))
        attack = next(a for a in fixtures.definition('SV045.Grapploct_52').abilities
                      if isinstance(a, Attack) and a.title == 'Slow-Acting Syncope')
        pay_cost(t, me, attack)
        await t.attack(me, 'Slow-Acting Syncope')
        self.assertEqual(len(t.session.scheduled_effects), 1)
        t.next_turn()
        ctx = EffectContext(t.session, P2, opp, None)
        await t._run(lambda: ctx.switch_active(P2, bench))
        await t._run(lambda: ctx.switch_active(P2, opp))
        await t.checkup()
        self.assertIn(opp, t.board.pokemon_in_play(P2))


if __name__ == "__main__":
    unittest.main()
