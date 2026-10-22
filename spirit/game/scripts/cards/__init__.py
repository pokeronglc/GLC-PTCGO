import os
import importlib.util
import logging
import sys
from typing import Dict, List
from spirit.game.models.card import Card, PokemonCard
from spirit.game.attributes import AttrID, CardType

class ScriptLoader:
    """Dynamically loads card definition scripts from the filesystem."""
    def __init__(self, scripts_dir: str, glc_only: bool = None):
        self.scripts_dir = os.path.abspath(scripts_dir)
        # Gym Leader Challenge server: only GLC-playable cards are cataloged.
        # Scripts that are not GLC-legal but are still imported by a legal
        # reprint stay on disk; they are executed but never registered.
        if glc_only is None:
            from spirit import config
            glc_only = config.GLC_ONLY
        self.glc_only = glc_only
        self.glc_skipped: List[str] = []
        self.cards: List[Card] = []
        self.cards_by_guid: Dict[str, Card] = {}
        self.cards_by_key: Dict[str, Card] = {}
        # script filename stem (e.g. "Watchog_79") -> archetype GUID
        self.cards_by_stem: Dict[str, str] = {}
        self.script_by_guid: Dict[str, str] = {}
        self.duplicate_guids: List[str] = []

    def load_all(self, force=False):
        """Loads all card scripts once; cached thereafter unless force=True.

        Re-running scripts rebuilds effect registries (ABILITIES_BY_ID etc.)
        and blocks the event loop ~1s, so hot paths must hit the cache.
        """
        if self.cards and not force:
            return self.cards
        self.cards = []
        self.cards_by_guid = {}
        self.cards_by_key = {}
        self.cards_by_stem = {}
        self.script_by_guid = {}
        self.duplicate_guids = []
        self.glc_skipped = []
        
        logging.info(f"[Scripts] Loading card scripts from {self.scripts_dir}...")
        
        for root, _, files in os.walk(self.scripts_dir):
            for file in files:
                if file.endswith(".py") and file != "__init__.py":
                    file_path = os.path.join(root, file)
                    self._load_script(file_path)
        # Unreleased sets are built in a separate folder (upcoming/<SET>) and
        # only loaded when SPIRIT_EXTRA_CARD_DIRS names them -- tests and dev
        # runs. The live server never sets it, so nothing there goes live.
        for extra in filter(None, os.environ.get("SPIRIT_EXTRA_CARD_DIRS", "").split(os.pathsep)):
            extra = os.path.abspath(extra)
            for root, _, files in os.walk(extra):
                for file in sorted(files):
                    if file.endswith(".py") and file != "__init__.py":
                        self._load_script(os.path.join(root, file))
        
        if self.duplicate_guids:
            details = "; ".join(self.duplicate_guids)
            raise RuntimeError(
                "Duplicate card GUIDs would crash the client while loading "
                f"archetypes: {details}"
            )

        # A few modules can be imported indirectly while the loader itself is
        # still resolving dependencies.  Run the normalization once more over
        # the authoritative registry after the full catalog is present; this
        # makes the result independent of filesystem/import order.
        from spirit.game.data_utils import CARD_DEFS_BY_GUID
        from spirit.game.card_effects.standard_era import (
            normalize_standard_card_definition,
        )
        for definition in CARD_DEFS_BY_GUID.values():
            normalize_standard_card_definition(definition)

        self._normalize_evolution_families()

        if self.glc_skipped:
            logging.info(
                f"[Scripts] Skipped {len(self.glc_skipped)} card scripts that are "
                "not playable in Gym Leader Challenge.")
        logging.info(f"[Scripts] Successfully loaded {len(self.cards)} card scripts.")
        return self.cards

    def _normalize_evolution_families(self):
        """Give every card of an evolution line its basic's family ID.

        The client groups an evolution line by family (the deck builder's
        "evolution line" view). Some imported printings carry their own
        species number instead (FLI Malamar 687 vs Inkay 686), splitting the
        line. The base-most ancestor that has a family wins."""
        import collections
        from spirit.game.data_utils import (
            CARD_DEFS_BY_GUID, PokemonCardDef, _string_attr, evolves_from_chain,
        )
        key = str(AttrID.FAMILY_ID.value)
        families = collections.defaultdict(collections.Counter)
        defs = [d for d in CARD_DEFS_BY_GUID.values() if isinstance(d, PokemonCardDef)]
        for d in defs:
            spec = d.extra_attributes.get(key)
            fam = spec.get("value") if isinstance(spec, dict) else None
            if fam:
                families[_string_attr(d, AttrID.EVOLUTION_LOGIC_NAME)][fam] += 1
        changed = 0
        for d in defs:
            chain = evolves_from_chain(d.guid)
            if not chain:
                # A Basic printing imported without a family (MEP Toxel)
                # takes the one its other printings agree on.
                spec = d.extra_attributes.get(key)
                own = spec.get("value") if isinstance(spec, dict) else None
                same = families.get(_string_attr(d, AttrID.EVOLUTION_LOGIC_NAME))
                if not own and same:
                    root = same.most_common(1)[0][0]
                    d.extra_attributes[key] = {"type": "int", "value": root}
                    card = self.cards_by_guid.get(d.guid)
                    if card is not None:
                        card.attributes[key] = {"type": "int", "value": root}
                    changed += 1
                continue
            root_family = None
            for name in chain:            # nearest first: keep the base-most hit
                if families.get(name):
                    root_family = families[name].most_common(1)[0][0]
            if not root_family:
                # Fossil lines start at an Item: fall back to what this
                # card's other printings use (MEP Tyrunt).
                spec = d.extra_attributes.get(key)
                same = families.get(_string_attr(d, AttrID.EVOLUTION_LOGIC_NAME))
                if same and not (isinstance(spec, dict) and spec.get("value")):
                    root_family = same.most_common(1)[0][0]
            if not root_family:
                continue
            spec = d.extra_attributes.get(key)
            if isinstance(spec, dict) and spec.get("value") == root_family:
                continue
            d.extra_attributes[key] = {"type": "int", "value": root_family}
            card = self.cards_by_guid.get(d.guid)
            if card is not None:
                card.attributes[key] = {"type": "int", "value": root_family}
            changed += 1
        if changed:
            logging.info(f"[Scripts] Aligned {changed} evolution-line family IDs.")

    def _load_script(self, file_path: str):
        """Loads a single card script."""
        from spirit.game.excluded_prints import excluded_print
        # Ignore an obsolete script left by an older non-Git installation.
        stem = os.path.splitext(os.path.basename(file_path))[0]
        set_dir = os.path.basename(os.path.dirname(file_path))
        if excluded_print(set_dir, stem.rsplit('_', 1)[-1]):
            return
        if self.glc_only:
            from spirit.game.glc import EXCLUDED_SETS
            if set_dir in EXCLUDED_SETS:
                self.glc_skipped.append(file_path)
                return
        try:
            # Create a unique module name based on the relative path
            rel_path = os.path.relpath(file_path, self.scripts_dir)
            if rel_path.startswith(".."):
                # Extra (unreleased) set folder: name the module by set + file.
                rel_path = os.path.join(set_dir, os.path.basename(file_path))
            module_name = "card_script_" + rel_path.replace(os.path.sep, "_").replace(".py", "")
            
            spec = importlib.util.spec_from_file_location(module_name, file_path)
            if spec is None or spec.loader is None:
                logging.error(f"[Scripts] Could not create spec or loader for {file_path}")
                return

            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            if hasattr(module, 'card'):
                card_def = module.card
                # Bulk-imported catalogs use a shared text interpreter.  Fix
                # Ability/trigger/passive classification before attributes and
                # legal actions are registered.  Hand-written effects are not
                # touched by this normalization.
                try:
                    from spirit.game.card_effects.standard_era import (
                        normalize_standard_card_definition,
                    )
                    normalize_standard_card_definition(card_def)
                except Exception as normalize_error:
                    logging.error(
                        f"[Scripts] Failed to normalize {file_path}: "
                        f"{normalize_error}"
                    )
                if self.glc_only:
                    from spirit.game.glc import is_glc_legal
                    if not is_glc_legal(card_def):
                        self.glc_skipped.append(file_path)
                        return
                # Convert the Definition object into a Server Card model
                # This ensures compatibility with existing packet handlers
                archetype = card_def.to_archetype_dict()
                guid = archetype["guid"]
                key = archetype["key"]
                attrs = archetype["attributes"]
                # A foil the client can't render without mask textures makes
                # the whole card invisible; fall back to a plain card.
                from spirit.game.foil_masks import strip_unrenderable_foil
                strip_unrenderable_foil(attrs, file_path, self.scripts_dir)

                if guid in self.cards_by_guid:
                    first = self.script_by_guid.get(guid, "<unknown>")
                    duplicate = (
                        f"{guid}: {first} and {file_path}"
                    )
                    logging.error(f"[Scripts] Duplicate card GUID: {duplicate}")
                    self.duplicate_guids.append(duplicate)
                    return
                
                c_type = attrs.get(str(AttrID.CARD_TYPE.value), {}).get("value", CardType.UNSET)
                
                display_name = archetype.get("display_name")
                searchable_by = archetype.get("searchable_by", [])
                subtypes = getattr(card_def, "subtypes", [])

                if c_type == CardType.POKEMON:
                    card_obj = PokemonCard(guid, key, attrs, display_name, searchable_by, subtypes)
                else:
                    card_obj = Card(guid, key, attrs, display_name, searchable_by, subtypes)
                
                self.cards.append(card_obj)
                self.cards_by_guid[guid] = card_obj
                self.script_by_guid[guid] = file_path
                self.cards_by_key[key] = card_obj
                self.cards_by_stem[os.path.splitext(os.path.basename(file_path))[0]] = guid
            else:
                logging.warning(f"[Scripts] Script {file_path} does not define a 'card' object.")
                
        except Exception as e:
            logging.error(f"[Scripts] Failed to load script {file_path}: {e}")

# Global loader instance
SCRIPTS_DIR = os.path.join(os.path.dirname(__file__))
loader = ScriptLoader(SCRIPTS_DIR)

# Dev/test only: let "spirit.game.scripts.cards.<SET>.<Card>" imports resolve
# for an unreleased set kept outside the live folder (see load_all).
for _extra in filter(None, os.environ.get("SPIRIT_EXTRA_CARD_DIRS", "").split(os.pathsep)):
    _extra = os.path.abspath(_extra)
    if _extra not in __path__:
        __path__.append(_extra)
