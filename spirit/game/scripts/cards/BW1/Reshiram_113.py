from spirit.game.scripts.cards.BW4.Reshiram_21 import card as base_card
from spirit.game.data_utils import reprint
from spirit.game.attributes import Rarities


# Same card text as BW4.21: share its code so every printing behaves alike.
card = reprint(
    base_card,
    collector_number=113,
    rarity=Rarities.RareUltra,
    guid="9c471b53-b6f0-5acd-a4f4-3019b940f1e2",
    set_code="BW1",
    key="BW1",
)
