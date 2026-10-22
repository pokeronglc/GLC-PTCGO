"""Localization strings for UI concepts newer than the archived client DB.

The bundled localization database predates Sword & Shield and Scarlet &
Violet.  The patched client can render/filter those cards, but asks for keys
that do not exist in that old database.  Unknown localization IDs are shown
verbatim, so keep the compatibility additions in this small, auditable table.

Keys are lowercase to match the original database.  The client localizer is
case-insensitive (set block values themselves are sent as ``SWSH``/``SV``).
"""
import re


SERIES_LOCALIZATION_OVERRIDES = {
    # Expansion groups introduced after the last official PTCGO strings.
    "collection.filter.series.swsh": "<i>Sword & Shield</i> Series",
    "collection.filter.series.sv": "<i>Scarlet & Violet</i> Series",
    # The NONE block is reserved for the custom Mega Evolution-era sets.
    "collection.filter.series.none": "<i>Mega Evolution</i> Series",
}


# The archived localization database ends partway through Sun & Moon.  SetData
# only carries the short set key, so the deck builder asks the localizer for
# ``set.name.<key>`` when it draws each expansion filter.
SET_NAME_LOCALIZATION_OVERRIDES = {
    # Later Sun & Moon expansions.
    "set.name.sm7": "<i>Sun & Moon—Celestial Storm</i>",
    "set.name.dm": "<i>Dragon Majesty</i>",
    "set.name.sm8": "<i>Sun & Moon—Lost Thunder</i>",
    "set.name.sm9": "<i>Sun & Moon—Team Up</i>",
    "set.name.gum": "<i>Detective Pikachu</i>",
    "set.name.sm10": "<i>Sun & Moon—Unbroken Bonds</i>",
    "set.name.sm11": "<i>Sun & Moon—Unified Minds</i>",
    "set.name.hf": "<i>Hidden Fates</i>",
    "set.name.sm12": "<i>Sun & Moon—Cosmic Eclipse</i>",

    # Sword & Shield expansions.
    "set.name.promo_swsh": "<i>Sword & Shield</i> Black Star Promos",
    "set.name.swsh1": "<i>Sword & Shield</i>",
    "set.name.swsh2": "<i>Sword & Shield—Rebel Clash</i>",
    "set.name.swsh3": "<i>Sword & Shield—Darkness Ablaze</i>",
    "set.name.swsh35": "<i>Champion's Path</i>",
    "set.name.swsh4": "<i>Sword & Shield—Vivid Voltage</i>",
    "set.name.swsh45": "<i>Shining Fates</i>",
    "set.name.swsh5": "<i>Sword & Shield—Battle Styles</i>",
    "set.name.swsh6": "<i>Sword & Shield—Chilling Reign</i>",
    "set.name.swsh7": "<i>Sword & Shield—Evolving Skies</i>",
    "set.name.ann25thr": "<i>Celebrations—Classic Collection</i>",
    "set.name.cel25": "<i>Celebrations</i>",
    "set.name.swsh8": "<i>Sword & Shield—Fusion Strike</i>",
    "set.name.swsh9": "<i>Sword & Shield—Brilliant Stars</i>",
    "set.name.swsh10": "<i>Sword & Shield—Astral Radiance</i>",
    "set.name.pgo": "<i>Pokémon GO</i>",
    "set.name.swsh11": "<i>Sword & Shield—Lost Origin</i>",
    "set.name.swsh12": "<i>Sword & Shield—Silver Tempest</i>",
    "set.name.cz": "<i>Crown Zenith</i>",

    # Scarlet & Violet expansions present in this server.
    "set.name.sve": "<i>Scarlet & Violet Energies</i>",
    "set.name.sv1": "<i>Scarlet & Violet</i>",
    "set.name.sv2": "<i>Scarlet & Violet—Paldea Evolved</i>",
    "set.name.sv3": "<i>Scarlet & Violet—Obsidian Flames</i>",
    "set.name.sv035": "<i>Scarlet & Violet—151</i>",
    "set.name.sv4": "<i>Scarlet & Violet—Paradox Rift</i>",
    "set.name.sv045": "<i>Scarlet & Violet—Paldean Fates</i>",
    "set.name.sv05": "<i>Scarlet & Violet—Temporal Forces</i>",
    "set.name.sv06": "<i>Scarlet & Violet—Twilight Masquerade</i>",
    "set.name.sv065": "<i>Scarlet & Violet—Shrouded Fable</i>",
    "set.name.sv07": "<i>Scarlet & Violet—Stellar Crown</i>",
    "set.name.sv08": "<i>Scarlet & Violet—Surging Sparks</i>",
    "set.name.sv085": "<i>Scarlet & Violet—Prismatic Evolutions</i>",
    "set.name.sv09": "<i>Scarlet & Violet—Journey Together</i>",
    "set.name.sv10": "<i>Scarlet & Violet—Destined Rivals</i>",
    "set.name.rsv10pt5": "<i>Scarlet & Violet—White Flare</i>",
    "set.name.zsv10pt5": "<i>Scarlet & Violet—Black Bolt</i>",
    "set.name.svp": "<i>Scarlet & Violet</i> Black Star Promos",

    # Additional catalog groups supported by the fork.
    "set.name.mee": "<i>Mega Evolution Energies</i>",
    "set.name.me1": "<i>Mega Evolution</i>",
    "set.name.me2": "<i>Phantasmal Flames</i>",
    "set.name.me2pt5": "<i>Ascended Heroes</i>",
    "set.name.me3": "<i>Perfect Order</i>",
    "set.name.me4": "<i>Chaos Rising</i>",
    "set.name.me5": "<i>Pitch Black</i>",
    "set.name.me55": "<i>30th Celebration</i>",
    "set.name.mep": "<i>Mega Evolution</i> Black Star Promos",
}


CARD_FILTER_LOCALIZATION_OVERRIDES = {
    "deckbuilder.cardfilters.attributes.nonfoil": "Non-Foil",
    "deckbuilder.cardfilters.attributes.parallelfoil": "Reverse Holo",
    "deckbuilder.cardfilters.attributes.specialfoil": "Regular Holo",
    "deckbuilder.cardfilters.attributes.shinypokemon": "Shining Pokémon",
    "deckbuilder.cardfilters.attributes.tag_team": "TAG TEAM",
    "deckbuilder.cardfilters.attributes.pokemon_v": "Pokémon V",
    # Battle Style attributes added by the GX-support client fork.
    "deckbuilder.cardfilters.attributes.single_strike": "Single Strike",
    "deckbuilder.cardfilters.attributes.rapid_strike": "Rapid Strike",
    "deckbuilder.cardfilters.attributes.fusion_strike": "Fusion Strike",
}


# Gym Leader Challenge server.  GLC rides the client's *Standard* slot (the
# only constructed format the client's Versus screen offers besides Expanded,
# Legacy and Theme), so every archived string that says "Standard" is
# relabelled "Gym Leader Challenge" (see relabel_archived_string below).
# Expanded / Legacy / Theme are hard-coded in the client's menus; no deck is
# ever valid for them here, so their labels say they are not available.
# If a long label is clipped in the client, shorten GLC_NAME (e.g. "GLC").
GLC_NAME = "Gym Leader Challenge"
GLC_RULES = (
    "60 cards, one Pokémon type, only one copy of each card except basic "
    "Energy, and no Rule Box Pokémon or ACE SPEC cards."
)
_NOT_AVAILABLE = f"Not available on this server. Use {GLC_NAME}."
_OFF = "(Not Available)"
_BLANK = "--"

FORMAT_LOCALIZATION_OVERRIDES = {
    "createnewdeck.standardbuttondescription.label": f"Create a {GLC_NAME} deck: {GLC_RULES}",
    "com.direwolfdigital.cake.trainerchallenge.zachdeckcallout.modifiedselected": f"{GLC_NAME}: {GLC_RULES}",
    "landing.trainertip.12": f"{GLC_NAME}: {GLC_RULES}",
    "landing.trainertip.13": f"This server plays {GLC_NAME}. Create your decks as {GLC_NAME} decks in the Deck Manager.",
    "newuserexperience.fullscreen.deckbuilderintro.dialog3": f"This server plays {GLC_NAME}.",
    "tournament.decktype.standard": GLC_NAME,
    # Formats that exist in the client menus but not on this server.
    "versusscreen.queuedropdown.expanded": "{expandedqueue} Expanded " + _OFF,
    "versusscreen.queuedropdown.legacy": "{legacyqueue} Legacy " + _OFF,
    "versusscreen.queuedropdown.theme": "{themequeue} Theme " + _OFF,
    # Create a New Deck: only Gym Leader Challenge and Import matter here, so
    # the other buttons are blanked to keep players' eyes on those two.
    "createnewdeck.deckwizardbutton.label": _BLANK,
    "createnewdeck.deckwizardbuttondescription.label": _BLANK,
    "createnewdeck.expandedbutton.label": _BLANK,
    # The Expanded button has no key of its own; its layout reads the Deck
    # Manager's Expanded tab label (sharedassets10).
    "cakedeckmanager.deckmanagement.tab.expanded": _BLANK,
    "createnewdeck.expandedbuttondescription.label": _BLANK,
    "createnewdeck.legacybutton.label": _BLANK,
    "createnewdeck.legacybuttondescription.label": _BLANK,
    "createnewdeck.unlimitedbutton.label": _BLANK,
    "createnewdeck.unlimitedbuttondescription.label": _BLANK,
}

# Archived strings whose "Standard" is the format name.  Shop bundles,
# product text, challenges and prize names keep their original wording.
_STANDARD_WORD = re.compile(r"\bStandard\b")
_KEEP_PREFIXES = (
    "product.", "com.direwolfdigital.cake.data.", "eula", "tournaments.prizetype",
    "challenge.",
)


def relabel_archived_string(key: str, value: str) -> str:
    """Rename the Standard format to Gym Leader Challenge in UI strings."""
    lowered = key.lower()
    if not value or "Standard" not in value or lowered[:1].isdigit() \
            or lowered.startswith(_KEEP_PREFIXES):
        return value
    return _STANDARD_WORD.sub(GLC_NAME, value)


UI_LOCALIZATION_OVERRIDES = {
    **SERIES_LOCALIZATION_OVERRIDES,
    **SET_NAME_LOCALIZATION_OVERRIDES,
    **CARD_FILTER_LOCALIZATION_OVERRIDES,
    **FORMAT_LOCALIZATION_OVERRIDES,
}


def ui_localization_items():
    """Return fresh wire-ready entries without exposing the shared mapping."""
    return [
        {"key": key, "value": value}
        for key, value in UI_LOCALIZATION_OVERRIDES.items()
    ]
