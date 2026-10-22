# GLC meta card audit

This audit checked the 706 cards on the GLC meta list against how this server programs them.

## Results

- **Found on the server:** 698 cards, plus the 8 basic Energy, which need no programming. All of them are GLC-legal, so none were removed by the prune.
- **Crash test:** every attack, Ability, Trainer, Stadium, Tool and Energy effect on the list was run on a test board. None crashed, and no card is marked as unimplemented.
- **Skipped in the crash test:** 57 effects, listed below. They were skipped only because their play condition wasn't met on the test board, for example "needs a damaged Pokémon" or "needs a Stadium in play". Most of them are covered by the existing rule tests.
- **Hand checks:** 27 cards with complex rules were checked by hand or with new tests (`tests/test_glc_meta_cards.py`).

## Bugs fixed

- **Colress's Tenacity (SFA 57):** if your deck had no Stadium left, or no Energy left, you got nothing and the deck wasn't shuffled. It now takes whichever of the two it finds and always shuffles.
- **U-Turn Board / Recycle Energy:** fixed earlier. They no longer send the knocked-out Pokémon to your hand.
- **Charizard PGO / Gardevoir NXD Energy doubling:** fixed earlier. Discard costs no longer take extra Energy cards.

## Second sweep

Every meta-list Trainer and every meta-list Pokémon that recovers cards from the discard pile was run on a full test board, including the 57 effects skipped in the first crash test. Fixed:

- **Ditto (BCR 108), Transform:** the Ability couldn't be used at all, because its wording ("During your turn (before your attack)") has no "once" and the card loader turned it into a passive. It's usable again, and Ditto now stays underneath the new Pokémon instead of going to the discard pile.
- **Tate & Liza:** always shuffled your hand and drew 5. It now asks which of its two options you want.
- **Lanturn (LOT 74), Salvage:** let you shuffle any 4 cards, twice. It now shuffles 4 Item cards once.

Earlier rounds also fixed Brigette and 15 other Trainer searches, Salvatore, Joltik's Jolting Charge and Pelipper's Hearsay.

## Matched by a guess

These lines on the list didn't give an exact set and number match, so I matched them another way. Please check they're the cards you meant.

- `Charmeleon GEN 4 (Call for Support)` → `TwentiethAnn/Charmeleon_104.py` (by attack/ability name)
- `Slowpoke PGO` → `PGO/Slowpoke_19.py` (same set, other number)
- `Morpeko SHF SV044` → `SWSH45/Morpeko_36.py` (same set, other number)
- `Shuppet SVI 97 (Enveloping Shadow)` → `SV1/Shuppet_87.py` (by attack/ability name)
- `Machop MEW 151 (Mountain Mashing)` → `SV035/Machop_66.py` (by attack/ability name)
- `Zubat SFA 07 (Lead)` → `SV065/Zubat_27.py` (by attack/ability name)
- `Delicaty CES 12` → `SM7/Delcatty_121.py` (same set, other number)
- `Professor Juniper BW .27` → `BW10/ProfessorJuniper_84.py` (name only)
- `Dark Bell PLB 75` → `ME5/DarkBell_75.py` (same number, other set)
- `Brooklet Hill HIF SV88` → `HF/BrookletHill_188.py` (same set, other number)

## Skipped in the crash test

- Thwacky TWM 15 (Boom Boom Groove): Boom Boom Groove
- Delphox CRI 13 (Flaring Magic): Flaring Magic
- Slowbro PGO 20: Twilight Inspiration
- Slowpoke PGO: Ideal Fishing Day
- Alolamola BLK 24: Gentle Fin
- Munkidori TWM 95: Adrena-Brain
- Banette LOR 73: Puppet Offering
- Nihilego LOT 106: Nightcap
- Sableye LOR 70: Lost Mine
- Unown AOR 30: Farewell Letter
- Lunatone MEG 74: Lunar Cycle
- Garbodor RCL 118: Poisonous Puddle
- Revavroom SVI 142: Rumbling Engine
- Porygon Z UNB 157: Crazy Code
- Ace Trainer AOR 69: (on play)
- Blacksmith FLF 88: (on play)
- Cheryl BST 123: (on play)
- Delinquent BKP 98: (on play)
- Diantha FLI 105: (on play)
- Faba LOT 173: (on play)
- Lt. Surge's Strategy UNB 178: (on play)
- Lusamine CIN 96: (on play)
- Mela PAR 167: (on play)
- Philippe CRI 79: (on play)
- Raihan EVS 152: (on play)
- Team Yell's Cheer BRS 149: (on play)
- Teammates PRC 141: (on play)
- Thorton LOR 167: (on play)
- Aqua Patch GRI 119: (on play)
- Beast Ring FLI 102: (on play)
- Buddy Buddy Rescue BKT 135: (on play)
- Counter Catcher PAR 160: (on play)
- Dark Patch ASR 139: (on play)
- Devolution Spray EVO 76: (on play)
- Eco Arm AOR 71: (on play)
- Enhanced Hammer TWM 148: (on play)
- Field Blower GRI 125: (on play)
- Lana's Fishing Rod CEC 195: (on play)
- Lost Vacuum LOR 162: (on play)
- Max Revive XY 120: (on play)
- Metal Saucer SSH 170: (on play)
- Pal Pad SVI 182: (on play)
- Rescue Carrier CRZ 142: (on play)
- Rescue Stretcher GRI 130: (on play)
- Revitalizer GEN 70: (on play)
- Revive EVO 85: (on play)
- Sacred Ash DRI 168: (on play)
- Special Charge STS 105: (on play)
- Strange Timepiece MEG 128: (on play)
- Target Whistle PHF 106: (on play)
- VS Seeker PHF 109: (on play)
- Wondrous Patch PFL 94: (on play)
- Crystal Cave EVS 144: Crystal Cave
- Magma Basin BRS 144: Magma Basin
- Rough Seas PRC 137: Stadium Effect
- Shopping Center EVS 157: Shopping Center
- Surfing Beach MEG 129: Surfing Beach
