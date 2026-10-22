from spirit.game.scripts.cards.ME4.Ampharos_29 import card as base_card
from spirit.game.data_utils import reprint
from spirit.game.attributes import Rarities


# Same card text as ME4.29: share its code so every printing behaves alike.
card = reprint(
    base_card,
    collector_number=75,
    rarity=Rarities.Rare,
    guid="f560eb09-abb5-5444-8e1e-eb22200b4bee",
    set_code="MEP",
    key="MEP",
    regulation_mark="J",
)
