from spirit.game.data_utils import SupporterCardDef
from spirit.game.attributes import Rarities
# Same text as Avery 130: share its (fixed) effect so every printing behaves alike.
from spirit.game.scripts.cards.SWSH6.Avery_130 import avery


card = SupporterCardDef(
    guid="f5c2122f-e807-5e14-857f-bdbb7f24364d",
    key="SWSH6",
    name="com.direwolfdigital.cake.data.archetypes.trainer.Avery.Name",
    display_name="Avery",
    searchable_by=["Avery", "Supporter"],
    subtypes=["Supporter"],
    collector_number=211,
    set_code="SWSH6",
    rarity=Rarities.RareRainbow,
    effect=avery,
)
