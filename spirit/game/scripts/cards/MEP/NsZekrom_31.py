from spirit.game.scripts.cards.ME2PT5.NsZekrom_155 import card as base_card
from spirit.game.data_utils import reprint
from spirit.game.attributes import Rarities


# Same card text as ME2PT5.155: share its code so every printing behaves alike.
card = reprint(
    base_card,
    collector_number=31,
    rarity=Rarities.Rare,
    guid="35568388-a7fc-55c8-a32d-c7997a872d06",
    set_code="MEP",
    key="MEP",
    regulation_mark="I",
)
