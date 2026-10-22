from spirit.game.scripts.cards.CEL25.Pikachu_5 import card as base_card
from spirit.game.data_utils import reprint
from spirit.game.attributes import Rarities


# Same card text as CEL25.5: share its code so every printing behaves alike.
card = reprint(
    base_card,
    collector_number=35,
    rarity=Rarities.Common,
    guid='854192ed-096a-55cc-bcd7-bd098816758a',
    set_code='XY12',
    key='XY12',
)
