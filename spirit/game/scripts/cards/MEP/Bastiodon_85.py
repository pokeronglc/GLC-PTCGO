from spirit.game.scripts.cards.ME5.Bastiodon_62 import card as base_card
from spirit.game.data_utils import reprint
from spirit.game.attributes import Rarities


# Same card text as ME5.62: share its code so every printing behaves alike.
card = reprint(
    base_card,
    collector_number=85,
    rarity=Rarities.Rare,
    guid="02f8b55a-2879-5657-ab38-6af37e457944",
    set_code="MEP",
    key="MEP",
    regulation_mark="J",
)
