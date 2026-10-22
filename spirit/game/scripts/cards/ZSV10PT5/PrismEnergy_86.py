from spirit.game.scripts.cards.BW4.PrismEnergy_93 import card as base_card
from spirit.game.data_utils import reprint
from spirit.game.attributes import Rarities


# Same card text as Prism Energy NXD 93 (tested): every type of Energy, one
# at a time, on a Basic Pokémon; Colorless otherwise.  Share its code so
# every printing behaves alike.
card = reprint(
    base_card,
    collector_number=86,
    rarity=Rarities.Uncommon,
    guid="f7570c28-92a7-5fe1-9fdb-901004795357",
    set_code="ZSV10PT5",
    key="ZSV10PT5",
    regulation_mark="I",
)
