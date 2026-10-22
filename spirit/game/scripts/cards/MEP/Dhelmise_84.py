from spirit.game.scripts.cards.ME5.Dhelmise_39 import card as base_card
from spirit.game.data_utils import reprint
from spirit.game.attributes import Rarities


# Same card text as ME5.39: share its code so every printing behaves alike.
card = reprint(
    base_card,
    collector_number=84,
    rarity=Rarities.Rare,
    guid="fb6660ee-bb19-5e4f-a8d2-3f953e7f8c42",
    set_code="MEP",
    key="MEP",
    regulation_mark="J",
)
