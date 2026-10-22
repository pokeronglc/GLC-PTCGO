from spirit.game.scripts.cards.BW2.Tornadus_89 import card as base_card
from spirit.game.data_utils import reprint
from spirit.game.attributes import Rarities


# Same card text as BW2.89: share its code so every printing behaves alike.
card = reprint(
    base_card,
    collector_number=98,
    rarity=Rarities.RareUltra,
    guid="32820dcc-2e97-5b4a-8b0b-8bd5b6577fe5",
    set_code="BW2",
    key="BW2",
)
