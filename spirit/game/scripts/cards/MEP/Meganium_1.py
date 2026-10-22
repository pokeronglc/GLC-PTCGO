from spirit.game.scripts.cards.ME1.Meganium_10 import card as base_card
from spirit.game.data_utils import reprint
from spirit.game.attributes import Rarities


# Same card text as ME1.10: share its code so every printing behaves alike.
card = reprint(
    base_card,
    collector_number=1,
    rarity=Rarities.Rare,
    guid="79c2e1cf-fb07-549c-b91c-78244bb60438",
    set_code="MEP",
    key="MEP",
    regulation_mark="I",
)
