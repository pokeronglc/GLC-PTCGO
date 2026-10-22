from spirit.game.scripts.cards.ME1.Riolu_76 import card as base_card
from spirit.game.data_utils import reprint
from spirit.game.attributes import Rarities


# Same card text as ME1.76: share its code so every printing behaves alike.
card = reprint(
    base_card,
    collector_number=10,
    rarity=Rarities.Rare,
    guid="f2f02ae4-e34b-5324-8ceb-d7ae22076f4b",
    set_code="MEP",
    key="MEP",
    regulation_mark="I",
)
