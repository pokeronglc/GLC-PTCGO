# Gym Leader Challenge server

GLC-PTCGO is set up as a **Gym Leader Challenge (GLC) only** server.

## What changed

- **One format.** Gym Leader Challenge rides the client's **Standard** slot, since that is the format the client's Versus screen offers. Every client label that said "Standard" now says "Gym Leader Challenge" (`spirit/game/localization_overrides.py`). `formats.json` also keeps Unlimited, with the same GLC card pool, for friend challenges and tournaments. Expanded, Legacy and Theme are hard-coded in the client's menus and can't be removed from the server side, so they are labelled "(Not Available)" and no deck is ever valid for them.
- **Only GLC-playable cards.** `spirit/game/glc.py` defines the card pool:
  - Black & White onward. The HeartGold & SoulSilver sets (HGSS1-4, Call of Legends, HGSS promos) are excluded.
  - No Rule Box Pokémon: EX, GX, TAG TEAM, V, VMAX, VSTAR, V-UNION, ex, Mega, BREAK, Prism Star and Radiant.
  - No ACE SPEC cards.
  - The GLC ban list.

  The card loader skips everything else (`SPIRIT_GLC_ONLY=1`, the default).
- **The bot's deck** in `spirit/game/starter_content.py` is a GLC-legal mono-Psychic singleton deck.

## Removing the non-GLC files

Stop the server, then from the repository root run:

```powershell
python -m spirit.tools.prune_to_glc --dry-run   # see what will be removed
python -m spirit.tools.prune_to_glc             # remove it
```

The prune tool does the following:

- Deletes the non-GLC card scripts, their artwork, foil masks and pip crops.
- Deletes the compiled bundles of every set that lost cards. These are rebuilt smaller the next time the server starts, so the first start takes longer.
- Removes those cards from accounts and saved decks in `ptcgo_server.db`. It backs up the database to `ptcgo_server.db.pre-glc-*.bak` first. Use `--keep-db` to leave the database alone.
- Writes `spirit/database/json_data/glc_removed_cards.json`, which keeps any old copies of removed cards hidden.

Run it again after you edit the ban list in `spirit/game/glc.py`.

On a new VPS, run the prune **before** `python -m spirit.tools.install_recent_card_art`. That way only GLC card art is downloaded.

## Landing-page background

Put a 16:9 PNG (1920×1080 is best) in `spirit/assets/landing_pages/`, for example `glc.png`. At startup the server builds it into the `en_US_LandingPage_Custom` bundle. Then open `http://<server>:8000/admin`, go to **Dynamic Pages**, create a landing page, and pick that artwork as its background.

If an original `en_US_LandingPage_*` bundle is available (from `INSTALL_BUNDLES.txt` option B, or through `PTCGO_CACHE_DIR`), the server uses it as the template. If not, it falls back to the card-bundle template that ships with the server. That fallback hasn't been tested in the game client yet: if the landing page shows up blank or broken, add an original LandingPage bundle.

## Deck rules

The deck validator applies the GLC deck-building rules to every format while `SPIRIT_GLC_ONLY=1` (`deck_rule_failures` in `spirit/game/glc.py`):

- **Singleton.** Only one copy of each card name, except basic Energy. Name variants count as the same name: "Professor's Research (Professor Turo)" is "Professor's Research", and Lysandre is the same card as Boss's Orders.
- **One Pokémon type.** Every Pokémon must share a type. A dual-type Pokémon fits a deck of either of its types.
- **60 cards** and **at least one Basic Pokémon**, as before.

A deck that breaks a rule shows as invalid in the deck builder and can't be used to queue.

## New accounts

Every account is set to exactly 1 copy of every card each time it logs in (`SPIRIT_GRANT_ALL_CARDS_ON_LOGIN=1`, the default), so new players can build any deck straight away and the deck builder can't add a second copy. Basic Energy is unlimited.

## Tests

The engine tests cover the full original catalog. Run them with `SPIRIT_GLC_ONLY=0`, before pruning. The tests for the removed Standard, Expanded and Legacy formats fail by design. `tests/test_glc_format.py` checks the GLC setup.
