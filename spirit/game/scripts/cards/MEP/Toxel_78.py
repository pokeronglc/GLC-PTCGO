from spirit.game.scripts.cards.ME2.Toxel_67 import card as base_card
from spirit.game.data_utils import reprint
from spirit.game.attributes import Rarities


# Same card text as ME2.67: share its code so every printing behaves alike.
card = reprint(
    base_card,
    collector_number=78,
    rarity=Rarities.Rare,
    guid="4af8c438-9446-5238-9a23-33a7a16ba851",
    set_code="MEP",
    key="MEP",
    regulation_mark="I",
)
