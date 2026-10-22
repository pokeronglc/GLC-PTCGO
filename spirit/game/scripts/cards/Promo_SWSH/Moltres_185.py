from spirit.game.scripts.cards.SWSH9.Moltres_21 import card as base_card
from spirit.game.data_utils import reprint
from spirit.game.attributes import Rarities


# Same card as Brilliant Stars Moltres 21: share its Inferno Wings code.
card = reprint(
    base_card,
    collector_number=185,
    rarity=Rarities.RarePromo,
    guid='f8b908a1-281e-5d51-90d4-676b7154995a',
    set_code='Promo_SWSH',
    key='Promo_SWSH',
    regulation_mark='F',
)

card.extra_attributes['200790'] = {'type': 'string', 'value': 'SWSH185'}
