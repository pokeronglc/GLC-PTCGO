# Alternate print of Grant (SWSH10 144); shares its effect and its
# discard-pile recovery action.
from spirit.game.scripts.cards.SWSH10.Grant_144 import card as base_card
from spirit.game.data_utils import reprint
from spirit.game.attributes import Rarities


card = reprint(
    base_card,
    collector_number=185,
    rarity=Rarities.RareUltra,
    guid='2155ebe8-9b1d-53b9-887b-903a962b7c43',
    set_code='SWSH10',
    key='SWSH10',
    regulation_mark=None,
)
