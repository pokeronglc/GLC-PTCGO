from spirit.game.scripts.cards.CZ.Lunatone_62 import card as base_card
from spirit.game.data_utils import reprint
from spirit.game.attributes import Rarities


# Same card text as CRZ 62, whose Moon Kinesis keeps the printed 30 base
# damage (30 + 30 per Psychic Energy); share its code so every printing
# behaves alike.
card = reprint(
    base_card,
    collector_number=34,
    rarity=Rarities.Uncommon,
    guid="81288712-7261-5003-9462-a3e56043a648",
    set_code="PGO",
    key="PGO",
)
