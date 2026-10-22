from spirit.game.scripts.cards.ME1.Alakazam_56 import card as base_card
from spirit.game.data_utils import reprint
from spirit.game.attributes import Rarities


# Same card text as ME1.56: share its code so every printing behaves alike.
card = reprint(
    base_card,
    collector_number=3,
    rarity=Rarities.Rare,
    guid="6abc06dd-1475-5faa-ad78-009e8502ea96",
    set_code="MEP",
    key="MEP",
    regulation_mark="I",
)
