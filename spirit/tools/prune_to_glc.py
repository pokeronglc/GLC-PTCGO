"""Prune this server down to Gym Leader Challenge (GLC) playable cards.

Deletes every card that is not playable in GLC (see spirit/game/glc.py):
its card script, its artwork / foil masks / pip crops, and the compiled set
bundles that contained it (they are rebuilt, smaller, on the next server
start).  It also records the removed card GUIDs so existing collections keep
working, and strips the removed cards from accounts and saved decks in
ptcgo_server.db (a backup is written first).

Stop the server first, then run from the repository root:

    python -m spirit.tools.prune_to_glc --dry-run   # report only
    python -m spirit.tools.prune_to_glc             # delete

Options:
    --dry-run     Report what would be removed; change nothing.
    --keep-db     Leave ptcgo_server.db untouched.

Safe to run again (e.g. after a GLC ban-list update in spirit/game/glc.py).
The next server start rebuilds the affected card bundles, which can take a
few minutes.
"""
import argparse
import glob
import json
import logging
import os
import re
import shutil
import sqlite3
import sys
import time

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SPIRIT = os.path.join(ROOT, "spirit")
SCRIPTS_DIR = os.path.join(SPIRIT, "game", "scripts", "cards")
ART_DIR = os.path.join(SPIRIT, "assets", "cards")
BUNDLE_DIR = os.path.join(SPIRIT, "assets", "bundleCache")
PIP_DIR = os.path.join(BUNDLE_DIR, "pips")
ASSET_MAP = os.path.join(SPIRIT, "server", "asset_map.json")
REMOVED_JSON = os.path.join(SPIRIT, "database", "json_data", "glc_removed_cards.json")
DB_PATH = os.path.join(ROOT, "ptcgo_server.db")

FOIL_SUFFIXES = ("_foil", "_foil_ph", "_foil_pcd", "_foil_secondary")
PIP_SUFFIXES = ("energypip", "toolpip")

_IMPORT_RE = re.compile(
    r"(?:from|import)\s+spirit\.game\.scripts\.cards\.([A-Za-z0-9_]+)\.([A-Za-z0-9_]+)")
_SIBLING_RE = re.compile(r"sibling_card\(\s*__file__\s*,\s*['\"]([^'\"]+)['\"]")


def _norm(path):
    return os.path.normcase(os.path.abspath(path))


def _script_dependencies(path):
    """Other card scripts a card script imports (cross-set reprints, siblings)."""
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()
    except OSError:
        return []
    deps = [os.path.join(SCRIPTS_DIR, s, f"{stem}.py") for s, stem in _IMPORT_RE.findall(text)]
    base = os.path.dirname(path)
    deps += [os.path.join(base, rel) for rel in _SIBLING_RE.findall(text)]
    return [_norm(d) for d in deps if os.path.isfile(d)]


def _size(path):
    try:
        return os.path.getsize(path)
    except OSError:
        return 0


def _dir_size(path):
    total = 0
    for root, _, files in os.walk(path):
        for name in files:
            total += _size(os.path.join(root, name))
    return total


def _mb(n):
    return f"{n / (1024 * 1024):,.1f} MB"


class Pruner:
    def __init__(self, dry_run):
        self.dry_run = dry_run
        self.freed = 0
        self.deleted_files = 0

    def delete_file(self, path):
        if not os.path.isfile(path):
            return
        self.freed += _size(path)
        self.deleted_files += 1
        if not self.dry_run:
            os.remove(path)

    def delete_tree(self, path):
        if not os.path.isdir(path):
            return
        self.freed += _dir_size(path)
        self.deleted_files += sum(len(f) for _, _, f in os.walk(path))
        if not self.dry_run:
            shutil.rmtree(path)


def classify():
    """Load every card script (GLC filter off) and split legal / removed."""
    from spirit.game.scripts.cards import ScriptLoader
    from spirit.game.data_utils import def_for
    from spirit.game.attributes import AttrID
    from spirit.game.glc import exclusion_reason

    full = ScriptLoader(SCRIPTS_DIR, glc_only=False)
    full.load_all()
    kept, removed = [], []
    for card in full.cards:
        definition = def_for(card.guid)
        path = _norm(full.script_by_guid[card.guid])
        entry = {
            "guid": card.guid.lower(),
            "set": definition.set_code,
            "number": card.get_attribute_value(AttrID.COLLECTOR_NUMBER),
            "name": getattr(definition, "display_name", None) or "",
            "script": path,
            "image": card.get_attribute_value(AttrID.IMAGE_URL),
            "vunion_stem": getattr(definition, "vunion_asset_stem", None),
        }
        reason = exclusion_reason(definition)
        if reason is None:
            kept.append(entry)
        else:
            entry["reason"] = reason
            removed.append(entry)
    return kept, removed


def needed_scripts(kept):
    """Kept scripts plus every script they import, transitively."""
    needed = set()
    stack = [entry["script"] for entry in kept]
    while stack:
        path = stack.pop()
        if path in needed:
            continue
        needed.add(path)
        stack.extend(_script_dependencies(path))
    return needed


def prune_files(pruner, removed, needed):
    kept_as_dependency = 0
    touched_sets = set()
    for entry in removed:
        script = entry["script"]
        set_dir = os.path.basename(os.path.dirname(script))
        stem = os.path.splitext(os.path.basename(script))[0]
        touched_sets.add(set_dir)
        touched_sets.add(entry["set"])

        if script in needed:
            # A GLC-legal reprint imports this script; keep the file (the
            # server's loader skips it) but still drop its artwork.
            kept_as_dependency += 1
        else:
            pruner.delete_file(script)
            for pyc in glob.glob(os.path.join(os.path.dirname(script), "__pycache__", f"{glob.escape(stem)}.*.pyc")):
                pruner.delete_file(pyc)

        art_dir = os.path.join(ART_DIR, set_dir)
        pruner.delete_file(os.path.join(art_dir, f"{stem}.png"))
        for suffix in FOIL_SUFFIXES:
            pruner.delete_file(os.path.join(art_dir, f"{stem}{suffix}.png"))
        if entry["vunion_stem"]:
            for path in glob.glob(os.path.join(art_dir, glob.escape(entry["vunion_stem"]) + "*.png")):
                pruner.delete_file(path)
        if entry["image"]:
            for suffix in PIP_SUFFIXES:
                pruner.delete_file(os.path.join(PIP_DIR, f"{entry['set']}_{entry['image']}_{suffix}.png"))
    return kept_as_dependency, touched_sets


def prune_bundles(pruner, touched_sets):
    """Delete compiled bundles of every set that lost cards (rebuilt on start)."""
    names = set()
    for set_code in touched_sets:
        names.add(f"en_US_{set_code}")
        for path in glob.glob(os.path.join(BUNDLE_DIR, f"en_US_{glob.escape(set_code)}_wp_*_Foil2")):
            names.add(os.path.basename(path))
    for name in sorted(names):
        pruner.delete_tree(os.path.join(BUNDLE_DIR, name))

    if os.path.isfile(ASSET_MAP):
        with open(ASSET_MAP, encoding="utf-8") as f:
            asset_map = json.load(f)
        stale = [k for k in asset_map if k in names]
        if stale and not pruner.dry_run:
            for key in stale:
                del asset_map[key]
            with open(ASSET_MAP, "w", encoding="utf-8") as f:
                json.dump(asset_map, f)
    return names


def remove_empty_dirs(pruner, base):
    if pruner.dry_run or not os.path.isdir(base):
        return
    for entry in os.listdir(base):
        path = os.path.join(base, entry)
        if not os.path.isdir(path) or entry.startswith("__"):
            continue
        cache = os.path.join(path, "__pycache__")
        remaining = [n for n in os.listdir(path) if n != "__pycache__"]
        if not remaining:
            if os.path.isdir(cache):
                shutil.rmtree(cache)
            os.rmdir(path)


def write_removed_json(removed, dry_run):
    """Merge with earlier runs: cards deleted then can no longer be loaded."""
    entries = {}
    if os.path.isfile(REMOVED_JSON):
        try:
            with open(REMOVED_JSON, encoding="utf-8") as f:
                for entry in json.load(f).get("cards", []):
                    entries[entry["guid"]] = entry
        except (OSError, ValueError, KeyError):
            pass
    for entry in removed:
        entries[entry["guid"]] = {
            "guid": entry["guid"], "set": entry["set"], "number": entry["number"],
            "name": entry["name"], "reason": entry["reason"],
        }
    if dry_run:
        return len(entries)
    payload = {
        "description": "Cards removed by spirit/tools/prune_to_glc.py (not playable in "
                       "Gym Leader Challenge). Owned copies of these GUIDs are hidden.",
        "cards": sorted(entries.values(), key=lambda e: (str(e["set"]), int(e["number"] or 0))),
    }
    with open(REMOVED_JSON, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=1, ensure_ascii=False)
        f.write("\n")
    return len(entries)


def clean_database(removed_guids, dry_run):
    """Remove pruned cards from collections and saved decks."""
    if not os.path.isfile(DB_PATH):
        print("  No ptcgo_server.db found; nothing to clean.")
        return
    src = sqlite3.connect(DB_PATH, timeout=30)
    try:
        tables = {r[0] for r in src.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        rows = []
        if "collection" in tables:
            rows = [r for r in src.execute("SELECT rowid, archetype_id FROM collection")
                    if str(r[1]).lower() in removed_guids]
        decks = []
        if "decks" in tables:
            for deck_id, data in src.execute("SELECT id, deck_data FROM decks"):
                try:
                    deck = json.loads(data)
                except (TypeError, ValueError):
                    continue
                changed = False
                for key in ("piles", "cards"):
                    piles = deck.get(key)
                    if not isinstance(piles, dict):
                        continue
                    for pile, cards in piles.items():
                        if isinstance(cards, list):
                            kept = [g for g in cards if str(g).lower() not in removed_guids]
                            if len(kept) != len(cards):
                                piles[pile] = kept
                                changed = True
                if changed:
                    decks.append((json.dumps(deck), deck_id))
        print(f"  Collection stacks to remove: {len(rows)}; saved decks to update: {len(decks)}")
        if dry_run or (not rows and not decks):
            return
        backup = DB_PATH + time.strftime(".pre-glc-%Y%m%d-%H%M%S.bak")
        dst = sqlite3.connect(backup)
        with dst:
            src.backup(dst)
        dst.close()
        print(f"  Backup written: {os.path.relpath(backup, ROOT)}")
        with src:
            src.executemany("DELETE FROM collection WHERE rowid = ?", [(r[0],) for r in rows])
            src.executemany("UPDATE decks SET deck_data = ? WHERE id = ?", decks)
    finally:
        src.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--dry-run", action="store_true", help="report only, change nothing")
    parser.add_argument("--keep-db", action="store_true", help="leave ptcgo_server.db untouched")
    args = parser.parse_args(argv)

    os.chdir(ROOT)
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
    mode = "DRY RUN - nothing will be changed" if args.dry_run else "PRUNING"
    print(f"Gym Leader Challenge prune ({mode})")
    print("Loading every card script (this takes a minute)...")
    kept, removed = classify()
    needed = needed_scripts(kept)

    by_reason = {}
    for entry in removed:
        by_reason[entry["reason"]] = by_reason.get(entry["reason"], 0) + 1
    print(f"  GLC-playable cards kept: {len(kept)}")
    print(f"  Cards to remove:         {len(removed)}")
    for reason, count in sorted(by_reason.items(), key=lambda t: -t[1]):
        print(f"    {reason}: {count}")

    pruner = Pruner(args.dry_run)
    kept_dep, touched = prune_files(pruner, removed, needed)
    bundles = prune_bundles(pruner, touched)
    remove_empty_dirs(pruner, SCRIPTS_DIR)
    remove_empty_dirs(pruner, ART_DIR)
    total = write_removed_json(removed, args.dry_run)

    print(f"  Scripts kept only because a GLC reprint imports them: {kept_dep}")
    print(f"  Set bundles to rebuild on next start: {len(bundles)}")
    print(f"  Files {'to delete' if args.dry_run else 'deleted'}: {pruner.deleted_files} "
          f"({_mb(pruner.freed)})")
    print(f"  Removed-card list: {os.path.relpath(REMOVED_JSON, ROOT)} ({total} cards)")

    if args.keep_db:
        print("Database left untouched (--keep-db).")
    else:
        print("Cleaning ptcgo_server.db...")
        clean_database({e["guid"] for e in removed} | _all_removed_guids(), args.dry_run)

    if args.dry_run:
        print("Dry run complete. Run again without --dry-run to apply.")
    else:
        print("Done. Start the server; it rebuilds the affected card bundles first.")
    return 0


def _all_removed_guids():
    try:
        with open(REMOVED_JSON, encoding="utf-8") as f:
            return {e["guid"] for e in json.load(f).get("cards", [])}
    except (OSError, ValueError, KeyError):
        return set()


if __name__ == "__main__":
    sys.exit(main())
