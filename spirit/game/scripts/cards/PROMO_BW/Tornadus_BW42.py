from spirit.game.scripts.cards.BW2.Tornadus_89 import card as base_card
from spirit.game.data_utils import reprint
from spirit.game.attributes import Rarities


# Same card text as BW2.89: share its code so every printing behaves alike.
card = reprint(
    base_card,
    collector_number=42,
    rarity=Rarities.RarePromo,
    guid="9e881064-4354-555f-9a99-e9efa5332205",
    set_code="PROMO_BW",
    key="PROMO_BW",
)
