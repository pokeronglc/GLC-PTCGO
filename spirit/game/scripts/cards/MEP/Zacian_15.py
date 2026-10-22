from spirit.game.scripts.cards.ME2.Zacian_45 import card as base_card
from spirit.game.data_utils import reprint
from spirit.game.attributes import Rarities


# Same card text as ME2.45: share its code so every printing behaves alike.
card = reprint(
    base_card,
    collector_number=15,
    rarity=Rarities.Rare,
    guid="b17d4adc-4f29-5bc4-8cd6-be167fa4443e",
    set_code="MEP",
    key="MEP",
    regulation_mark="I",
)
