from spirit.game.card_effects.support_common import requires_hand
from spirit.game.data_utils import SupporterCardDef
from spirit.game.attributes import Rarities


# Same text as Caitlin 132: share its effect so every printing behaves alike.
from spirit.game.scripts.cards.SWSH6.Caitlin_132 import caitlin


card = SupporterCardDef(
    guid="24cf1f0f-cd1b-5d16-b9af-3a9760de0801",
    key="SWSH6",
    name="com.direwolfdigital.cake.data.archetypes.trainer.Caitlin.Name",
    display_name="Caitlin",
    searchable_by=["Caitlin", "Supporter"],
    subtypes=["Supporter"],
    collector_number=213,
    set_code="SWSH6",
    rarity=Rarities.RareRainbow,
    condition=requires_hand(),
    effect=caitlin
)
