from spirit.game.scripts.cards.BW2.Tornadus_89 import card as base_card
from spirit.game.data_utils import reprint
from spirit.game.attributes import Rarities


# Same card text as BW2.89: share its code so every printing behaves alike.
card = reprint(
    base_card,
    collector_number=108,
    rarity=Rarities.RareHolo,
    guid="51c8de8a-a1e6-5ddb-96da-8d3f8c29329c",
    set_code="BW11",
    key="BW11",
)
