from spirit.game.scripts.cards.BW9.Exeggcute_4 import card as base_card
from spirit.game.data_utils import reprint
from spirit.game.attributes import Rarities


# Same card text as BW9.4: share its code so every printing behaves alike.
card = reprint(
    base_card,
    collector_number=102,
    rarity=Rarities.RareSecret,
    guid="a0c73251-03d7-5750-9b82-f806ac3a4fa9",
    set_code="BW10",
    key="BW10",
)
