"""Which cards are being used in games, from the server log.

    cd /opt/glc-ptcgo && venv/bin/python -m spirit.tools.card_usage_report
    cd /opt/glc-ptcgo && venv/bin/python -m spirit.tools.card_usage_report --hours 48 --top 40

Two sources:
  * DECK lines (logged at every game start since the Oct 11 update): the
    full list of every deck taken into a game -> exact card usage.
  * Older logs only name some cards: Trainers played, Pokemon put on the
    Bench, and attacks / Abilities used.  Those are shown too, so there is
    something to look at before DECK lines build up.
Bot decks are left out of the deck counts. Each DECK line also carries the
deck type (GLC decks are one Pokemon type), so "Game over" lines give wins
by deck type for human-vs-human games.
"""
from __future__ import annotations

import argparse
import collections
import re
import subprocess
import sys

TS = re.compile(r"\d{4}-\d\d-\d\d \d\d:\d\d:\d\d,\d+ - \w+ - (.*)$")
DECK = re.compile(r"\[Session ([0-9a-f-]{36})\] DECK (.+?) <([^>]*)> \"(.*?)\" \((\d+)\): (.*)$")
OVER = re.compile(r"\[Session ([0-9a-f-]{36})\] Game over: (.+?) wins \((.*)\)")
CLAIMED = re.compile(r"\[Session ([0-9a-f-]{36})\] .+ claimed the win")


def result_kind(reason: str, claimed: bool) -> str:
    """'natural' (prizes / deck-out / no Pokémon left), 'concede', or 'left'
    (disconnect not returned, or AFK).  Before Oct 12 a disconnect win was
    logged as a concede; the 'claimed the win' line tells them apart."""
    r = reason.casefold()
    if r.endswith(" disconnected") or r.endswith(" was afk") or claimed:
        return "left"
    if r.endswith(" conceded"):
        return "concede"
    if "error" in r:
        return "error"
    return "natural"
ENTRY = re.compile(r"(\d+)x (.+) \[([^\]]*)\]$")
TRAINER = re.compile(r"\] (\S+) played trainer \S+ \((.+)\)\.$")
BENCH = re.compile(r"\] (\S+) benched \S+ \((.+)\)\.$")
ATTACK = re.compile(r"\] (\S+) attacks with '(.+)'\.$")
ABILITY = re.compile(r"\] (\S+) uses ability '(.+)'\.$")


def read_log(hours):
    cmd = ["journalctl", "-u", "glc", "--no-pager"]
    if hours:
        cmd += ["--since", f"-{int(hours * 60)}min"]
    out = subprocess.run(cmd, capture_output=True, text=True, errors="replace").stdout
    for raw in out.splitlines():
        if "[TCP] Sent " in raw or "[TCP] Included " in raw:
            continue
        m = TS.search(raw)
        if m:
            yield m.group(1)


INIT = re.compile(r"\[Session ([0-9a-f-]{36})\] Initializing (?:NetworkPlayer for (.+)\.|AI Bot)")
ACTOR = re.compile(r"\[Session ([0-9a-f-]{36})\] (\S+) (?:benched \S+ \((.+)\)|attacks with '(.+)'|uses ability '(.+)')\.$")


def _type_index():
    """name/attack/Ability title -> Counter of Pokemon types, from card data."""
    import json
    from spirit.game.scripts.cards import loader
    from spirit.game.data_utils import CARD_DEFS_BY_GUID, PokemonCardDef, Attack, _attr_value
    from spirit.game.attributes import AttrID, PokemonTypes
    loader.load_all()
    names, moves = (collections.defaultdict(collections.Counter) for _ in range(2))
    for d in CARD_DEFS_BY_GUID.values():
        if not isinstance(d, PokemonCardDef):
            continue
        raw = _attr_value(d, AttrID.POKEMON_TYPES, "[]") or "[]"
        for value in (json.loads(raw) if isinstance(raw, str) else raw):
            try:
                t = PokemonTypes(value).name.title()
            except Exception:
                continue
            names[d.display_name][t] += 1
            for a in getattr(d, "abilities", None) or []:
                moves[(isinstance(a, Attack), a.title)][t] += 1
    return names, moves


def _vote(votes, counter, weight):
    total = sum(counter.values())
    for t, n in counter.items():
        votes[t] += weight * n / total


def show(title, counter, top, unit):
    print(f"\n{title}: {len(counter)} different")
    for name, n in counter.most_common(top):
        print(f"  {n:5} {unit}  {name}")


def _plain_text(text):
    """Card text compared ignoring energy-symbol markup ("[ [Water] ]" vs
    "Water"), case and punctuation, so reprints with re-typeset text merge."""
    text = re.sub(r"\[\s*\[\s*(\w+)\s*\]\s*\]", r"\1", text or "")
    return " ".join(re.sub(r"[^a-z0-9]+", " ", text.casefold()).split())


def _functional_key(card: str, index: dict):
    """Cards that play the same count once: same name and the same attacks /
    Abilities (the official "same card" test), so exact reprints merge but
    two Inteleon with different attacks stay separate. Trainers and Energy
    merge by name. Anything not found in the card data stays its printing."""
    name, _, code = card.rpartition(" [")
    d = index.get(code.rstrip("]"))
    if d is None:
        return ("print", card)
    from spirit.game.data_utils import PokemonCardDef
    label = getattr(d, "display_name", None) or getattr(d, "name", None) or name
    if not isinstance(d, PokemonCardDef):
        return ("card", label)
    moves = tuple(sorted(
        (a.title or "", _plain_text(a.game_text),
         tuple(sorted((int(getattr(t, "value", t)), n)
                      for t, n in (getattr(a, "cost", None) or {}).items())),
         getattr(a, "damage", 0) or 0, getattr(a, "damage_operator", "") or "")
        for a in d.abilities if not getattr(a, "is_rule_action", False)))
    return ("pokemon", label, moves)


def _functional_counts(in_decks):
    """functional card -> decks containing it."""
    from spirit.game.scripts.cards import loader
    from spirit.game.data_utils import CARD_DEFS_BY_GUID
    loader.load_all()
    index = {}
    for d in CARD_DEFS_BY_GUID.values():
        index.setdefault(f"{d.set_code} {d.collector_number}", d)
    out = collections.Counter()
    for card, n in in_decks.items():
        out[_functional_key(card, index)] += n
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=float, default=0, help="0 = everything the log still holds")
    ap.add_argument("--top", type=int, default=25)
    args = ap.parse_args(argv)

    decks = 0
    in_decks = collections.Counter()      # card -> decks containing it
    copies = collections.Counter()        # card -> total copies
    trainers, bench, attacks, abilities = (collections.Counter() for _ in range(4))
    seen_deck = set()
    game_players = collections.defaultdict(set)   # game -> human names (+ "Bot")
    evidence = collections.defaultdict(list)      # (game, player) -> [(kind, name)]
    game_types = collections.defaultdict(dict)   # game -> {player: type}
    results = []                                  # (game, winner, reason)
    claimed_games = set()
    for msg in read_log(args.hours):
        m = DECK.search(msg)
        if m:
            game, who, dtype, _dname, _, body = m.groups()
            game_types[game][who] = dtype
            if who == "Bot" or (game, who) in seen_deck:
                continue
            seen_deck.add((game, who))
            decks += 1
            for part in body.split(" | "):
                e = ENTRY.match(part.strip())
                if e:
                    card = f"{e.group(2)} [{e.group(3)}]"
                    in_decks[card] += 1
                    copies[card] += int(e.group(1))
            continue
        m = INIT.search(msg)
        if m:
            game_players[m.group(1)].add(m.group(2) or "Bot")
        m = ACTOR.search(msg)
        if m:
            game, who, benched, attack, ability = m.groups()
            if benched:
                evidence[(game, who)].append(("name", benched))
            elif attack:
                evidence[(game, who)].append(("attack", attack))
            else:
                evidence[(game, who)].append(("ability", ability))
        m = CLAIMED.search(msg)
        if m:
            claimed_games.add(m.group(1))
        m = OVER.search(msg)
        if m:
            results.append((m.group(1), m.group(2), m.group(3)))
            continue
        for pat, counter in ((TRAINER, trainers), (BENCH, bench),
                             (ATTACK, attacks), (ABILITY, abilities)):
            m = pat.search(msg)
            if m and m.group(1) != "Bot":
                counter[m.group(2)] += 1
                break

    span = f"last {args.hours:g} h" if args.hours else "everything in the log"
    print(f"Card usage ({span})")
    if decks:
        print(f"\nDecks taken into games: {decks}")
        print(f"Different cards in those decks: {len(in_decks)}")
        names = collections.Counter()
        for card, n in in_decks.items():
            names[card.rsplit(" [", 1)[0]] += n
        print(f"Different card NAMES (all printings merged): {len(names)}")
        print(f"Different cards by what they do (exact reprints merged): "
              f"{len(_functional_counts(in_decks))}")
        show("Most-used cards (in how many decks)", in_decks, args.top, "decks")
    else:
        print("\nNo DECK lines yet (they start with the Oct 11 update) - "
              "showing what older logs name.")
    # Wins by deck type: human-vs-human games with both decks known.
    kinds = collections.Counter()
    human = [(g, w, r) for g, w, r in results
             if len(game_types.get(g, {})) == 2 and "Bot" not in game_types.get(g, {})]
    for g, w, r in human:
        kinds[result_kind(r, g in claimed_games)] += 1
    if human:
        print(f"\nHow human-vs-human games ended ({len(human)} games):")
        labels = {"natural": "Played out (prizes / deck-out / no Pokémon)",
                  "concede": "Conceded", "left": "Disconnected or AFK",
                  "error": "Server error"}
        for k in ("natural", "concede", "left", "error"):
            if kinds[k]:
                print(f"  {kinds[k]:5}  {labels[k]}")

    def wins_table(title, keep):
        record = collections.defaultdict(lambda: [0, 0])     # type -> [wins, games]
        mirror = 0
        for game, winner, reason in results:
            players = game_types.get(game, {})
            if len(players) != 2 or "Bot" in players or winner not in players:
                continue
            if not keep(result_kind(reason, game in claimed_games)):
                continue
            (a, ta), (b, tb) = players.items()
            if ta == tb:
                mirror += 1
                continue
            for who, t in ((a, ta), (b, tb)):
                record[t][1] += 1
                record[t][0] += who == winner
        if not record:
            return False
        counted = sum(g for _, g in record.values()) // 2
        print(f"\n{title} ({counted} games between different types; "
              f"{mirror} same-type games left out; bot games left out):")
        for t, (w, g) in sorted(record.items(), key=lambda kv: (-kv[1][0] / kv[1][1], -kv[1][1])):
            print(f"  {t:<10} {w:4} wins / {g:4} games  {100 * w / g:5.1f}%")
        return True

    # Owner ruling: a concede is a real win (the loser saw no way back);
    # only disconnects / AFK are left out of the main table.
    shown = wins_table("Wins by deck type (played out + concedes; disconnects/AFK left out)",
                       lambda k: k in ("natural", "concede"))
    shown = wins_table("Wins by deck type, ALL results (incl. disconnects/AFK)", lambda k: k != "error") or shown
    if shown:
        plays = collections.Counter()
        for game, players in game_types.items():
            for who, t in players.items():
                if who != "Bot":
                    plays[t] += 1
        show("Deck types taken into games", plays, args.top, "decks")
    if not decks and evidence:
        names, moves = _type_index()
        guessed = {}
        for (game, who), items in evidence.items():
            votes = collections.Counter()
            for kind, name in items:
                if kind == "name" and name in names:
                    _vote(votes, names[name], 1)
                elif kind == "attack" and (True, name) in moves:
                    _vote(votes, moves[(True, name)], 2)     # the attacker
                elif kind == "ability" and (False, name) in moves:
                    _vote(votes, moves[(False, name)], 1)
            if votes:
                ranked = votes.most_common(2)
                t, top_votes = ranked[0]
                second = ranked[1][1] if len(ranked) > 1 else 0
                # Enough evidence, and clearly ahead of the next type.
                if top_votes >= 1 and top_votes >= 1.5 * second:
                    guessed[(game, who)] = t
        plays = collections.Counter(t for (g, w), t in guessed.items() if w != "Bot")
        show("Deck types played (ESTIMATED from Pokemon/attacks seen; one per player per game)",
             plays, args.top, "decks")
        est = collections.defaultdict(lambda: [0, 0])
        counted = 0
        for game, winner, _reason in results:
            humans = [p for p in game_players.get(game, ()) if p != "Bot"]
            if len(game_players.get(game, ())) != 2 or len(humans) != 2 or winner not in humans:
                continue
            ta, tb = guessed.get((game, humans[0])), guessed.get((game, humans[1]))
            if not ta or not tb or ta == tb:
                continue
            counted += 1
            for who, t in ((humans[0], ta), (humans[1], tb)):
                est[t][1] += 1
                est[t][0] += who == winner
        if est:
            print(f"\nWins by deck type, ESTIMATED ({counted} human games between different types):")
            for t, (w, g) in sorted(est.items(), key=lambda kv: (-kv[1][0] / kv[1][1], -kv[1][1])):
                print(f"  {t:<10} {w:4} wins / {g:4} games  {100 * w / g:5.1f}%")
    show("Trainers played", trainers, args.top, "plays")
    show("Pokemon benched (Basics, by name)", bench, args.top, "times")
    show("Attacks used", attacks, args.top, "uses")
    show("Abilities used", abilities, args.top, "uses")
    return 0


if __name__ == "__main__":
    sys.exit(main())
