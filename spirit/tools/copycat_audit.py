"""Copycat audit: does every attack work when Mimikyu copies it?

For each GLC-legal attack with an effect this runs two otherwise identical
scenarios and compares the outcome:

  * control -- the card's own Pokémon uses the attack;
  * copy    -- Mimikyu (SM9 112) uses Copycat after the opponent's Pokémon
               used that attack last turn.

Both attackers carry the same Energy, the coin flips are seeded identically
and the Defending Pokémon has no Weakness/Resistance, so a correct copy
should change the board in the same way.  Differences are reported as:

  ERROR      the copy raised an exception (the control did not)
  NOTHING    the copy changed nothing although the control did
  DIFFERENT  both did something, but not the same thing

Some DIFFERENT results are legitimate (an attack that counts "this
Pokémon's" own name, HP or Benched copies behaves differently on Mimikyu),
so that list needs a human read.

    python -m spirit.tools.copycat_audit [--limit N] [--set SV08]
"""
from __future__ import annotations

import argparse
import asyncio
import collections
import json
import logging
import random
import sys
import traceback

from spirit.game.attributes import AttrID
from spirit.game.data_utils import Attack, CARD_DEFS_BY_GUID, PokemonCardDef
from spirit.game.models.board import EnergyEntity, PokemonEntity
from spirit.game.scripts.cards import loader
from spirit.game.session.effects import EffectContext
from spirit.game.session.passives import effective_max_hp
from spirit.tools.effect_smoke import (
    P1, P2, Rig, basic_energy_guids, pick_filler_basic, pick_filler_item,
)

COPYCAT = ("SM9", 112)
ZONES = ("hand", "deck", "discard", "bench", "prizePile", "lostZone")


def _definition(set_code, number):
    return next(d for d in CARD_DEFS_BY_GUID.values()
                if isinstance(d, PokemonCardDef) and d.set_code == set_code
                and d.collector_number == number)


def _neutral_defender(board):
    for pid in (P1, P2):
        for pokemon in board.pokemon_in_play(pid):
            pokemon.set_attribute(AttrID.HP, effective_max_hp(board, pokemon))
    active = board.active_pokemon(P2)
    if active is not None:
        active.set_attribute(AttrID.WEAKNESS_TYPES, [])
        active.set_attribute(AttrID.RESISTANCE_TYPES, [])


def _fingerprint(board):
    """Board facts an attack can change, keyed by board position."""
    out = {}
    for pid, side in ((P1, "me"), (P2, "opp")):
        for zone in ZONES:
            area = board.find_player_area(pid, zone)
            out[f"{side}.{zone}"] = len(area.children) if area is not None else 0
        pokemon = board.pokemon_in_play(pid)
        out[f"{side}.inplay"] = len(pokemon)
        active = board.active_pokemon(pid)
        if active is not None:
            out[f"{side}.active.damage"] = effective_max_hp(board, active) - active.get_attribute(AttrID.HP, 0)
            out[f"{side}.active.cond"] = tuple(sorted(active.get_attribute(AttrID.SPECIAL_CONDITIONS) or []))
            out[f"{side}.active.energy"] = len(board.attached_energies(active))
        bench = board.find_player_area(pid, "bench")
        out[f"{side}.bench.damage"] = tuple(sorted(
            effective_max_hp(board, p) - p.get_attribute(AttrID.HP, 0)
            for p in (bench.children if bench else []) if isinstance(p, PokemonEntity)))
    return out


def _delta(before, after):
    """What changed: counts as +/- differences, other facts as (old, new)."""
    out = {}
    for key in after:
        old, new = before.get(key), after.get(key)
        if old == new:
            continue
        out[key] = new - old if isinstance(new, int) and isinstance(old, int) else (old, new)
    return out


async def _run(rig, entities, attack, copy):
    board, session = rig.board, rig.session
    attacker = entities["p1_active"]
    if copy:
        copycat = next(a for a in _definition(*COPYCAT).abilities
                       if isinstance(a, Attack) and a.title == "Copycat")
        session.turn_state.attacks_used_last_turn = [
            (board.active_pokemon(P2).entity_id, attack._source_guid, attack.title)]
        ability = copycat
    else:
        ability = attack
    ctx = EffectContext(session, P1, attacker, ability)
    before = _fingerprint(board)
    random.seed(1234)
    await asyncio.wait_for(ability.effect(ctx), timeout=10)
    return _delta(before, _fingerprint(board))


def _copy_rig(target_def, filler, energies, item):
    """The control's exact board, with Mimikyu swapped in as the attacker.

    Same deck, Bench, hand and discard as the control, so effects that look
    for the original card by name (Multiply, Round, Call for Family) find
    the same cards; Mimikyu takes over the Active's attached Energy."""
    from spirit.game.models.board import create_card_entity
    rig = Rig(target_def, filler, energies, item)
    entities = rig.setup("pokemon")
    board = rig.board
    original = entities["p1_active"]
    active_area = board.find_player_area(P1, "activePokemonArea")
    mimikyu = create_card_entity(loader.cards_by_guid[_definition(*COPYCAT).guid.lower()], P1)
    mimikyu.owning_player_id = P1
    attachments = [card for card in list(original.children) if not isinstance(card, PokemonEntity)]
    active_area.remove_child(original)
    board.add_card_to_area(mimikyu, active_area)
    for card in attachments:
        board.attach_card(card.entity_id, mimikyu.entity_id)
    entities["p1_active"] = mimikyu
    return rig, entities


async def audit(limit=None, set_filter=None):
    loader.load_all()
    filler, energies, item = pick_filler_basic(), basic_energy_guids(), pick_filler_item()
    attacks = []
    for definition in CARD_DEFS_BY_GUID.values():
        if not isinstance(definition, PokemonCardDef) or definition.guid.lower() not in loader.cards_by_guid:
            continue
        if set_filter and definition.set_code != set_filter:
            continue
        for attack in definition.abilities or ():
            if isinstance(attack, Attack) and attack.effect is not None and not attack.gx:
                attack._source_guid = definition.guid
                attacks.append((definition, attack))
    attacks.sort(key=lambda pair: (pair[0].set_code, pair[0].collector_number, pair[1].title))
    if limit:
        attacks = attacks[:limit]

    results = collections.defaultdict(list)
    seen_texts = set()
    for definition, attack in attacks:
        key = (attack.title, attack.game_text, attack.damage)
        if key in seen_texts:          # identical reprints behave identically
            continue
        seen_texts.add(key)
        label = f"{definition.set_code} {definition.collector_number} {definition.display_name} - {attack.title}"
        try:
            rig = Rig(definition, filler, energies, item)
            entities = rig.setup("pokemon")
            _neutral_defender(rig.board)
            control = await _run(rig, entities, attack, copy=False)
        except Exception:
            continue                   # the attack itself fails without copying
        try:
            rig, entities = _copy_rig(definition, filler, energies, item)
            _neutral_defender(rig.board)
            copied = await _run(rig, entities, attack, copy=True)
        except Exception as e:
            results["ERROR"].append((label, f"{type(e).__name__}: {e}",
                                     traceback.format_exc(limit=4)))
            continue
        if control == copied:
            results["OK"].append(label)
        elif not copied:
            results["NOTHING"].append((label, control))
        else:
            results["DIFFERENT"].append((label, control, copied))
    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int)
    parser.add_argument("--set", dest="set_filter")
    parser.add_argument("--json")
    args = parser.parse_args()
    logging.disable(logging.CRITICAL)
    results = asyncio.run(audit(args.limit, args.set_filter))
    print(f"OK {len(results['OK'])}  ERROR {len(results['ERROR'])}  "
          f"NOTHING {len(results['NOTHING'])}  DIFFERENT {len(results['DIFFERENT'])}")
    for kind in ("ERROR", "NOTHING", "DIFFERENT"):
        for row in results[kind]:
            print(kind, row[0], "|", row[1] if kind != "DIFFERENT" else f"{row[1]} vs {row[2]}")
    if args.json:
        with open(args.json, "w", encoding="utf-8") as handle:
            json.dump({k: v for k, v in results.items()}, handle, indent=1, default=str)


if __name__ == "__main__":
    main()
