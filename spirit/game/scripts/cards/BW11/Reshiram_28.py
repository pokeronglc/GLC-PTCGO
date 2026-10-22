from spirit.game.scripts.cards.BW4.Reshiram_21 import card as base_card
from spirit.game.data_utils import reprint
from spirit.game.attributes import Rarities


# Same card text as BW4.21: share its code so every printing behaves alike.
card = reprint(
    base_card,
    collector_number=28,
    rarity=Rarities.RareHolo,
    guid="cc1ca7d2-e4f9-5863-9ee5-c9c5986bb6ce",
    set_code="BW11",
    key="BW11",
)
