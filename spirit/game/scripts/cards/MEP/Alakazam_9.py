from spirit.game.scripts.cards.ME1.Alakazam_56 import card as base_card
from spirit.game.data_utils import reprint
from spirit.game.attributes import Rarities


# Same card text as ME1.56: share its code so every printing behaves alike.
card = reprint(
    base_card,
    collector_number=9,
    rarity=Rarities.Rare,
    guid="18b0931b-bd50-527f-b7b3-3ed2b1be544e",
    set_code="MEP",
    key="MEP",
    regulation_mark="I",
)
