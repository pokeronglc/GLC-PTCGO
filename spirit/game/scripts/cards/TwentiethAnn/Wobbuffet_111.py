from spirit.game.scripts.cards.XY4.Wobbuffet_36 import card as base_card
from spirit.game.data_utils import reprint
from spirit.game.attributes import Rarities


# Same card text as XY4.36: share its code so every printing behaves alike.
card = reprint(
    base_card,
    collector_number=111,
    rarity=Rarities.Common,
    guid='2c947978-25c2-58b4-8ed6-65c29964defd',
    set_code='TwentiethAnn',
    key='TwentiethAnn',
)
