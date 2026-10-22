# Alternate print of Grant (SWSH10 144); shares its effect and its
# discard-pile recovery action.
from spirit.game.scripts.cards.SWSH10.Grant_144 import card as base_card
from spirit.game.data_utils import reprint
from spirit.game.attributes import Rarities


card = reprint(
    base_card,
    collector_number=203,
    rarity=Rarities.RareRainbow,
    guid='f53e3719-5220-5ebd-9254-216b6b23cab5',
    set_code='SWSH10',
    key='SWSH10',
    regulation_mark=None,
)
