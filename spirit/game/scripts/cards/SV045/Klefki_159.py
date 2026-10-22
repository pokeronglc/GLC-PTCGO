from spirit.game.scripts.cards.SV1.Klefki_96 import card as base_card
from spirit.game.data_utils import reprint
from spirit.game.attributes import Rarities


# Same card text as SV1.96: share its code so every printing behaves alike.
card = reprint(
    base_card,
    collector_number=159,
    rarity=Rarities.Rare,
    guid='483b35b7-bfe5-5b21-bdfe-03cbe0856a86',
    set_code='SV045',
    key='SV045',
    regulation_mark='G',
)
