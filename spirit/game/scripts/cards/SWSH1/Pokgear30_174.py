from spirit.game.data_utils import ItemCardDef
from spirit.game.attributes import Rarities
# Same text as Pokégear 3.0 SVI 186 (base of every other printing): share its effect.
from spirit.game.scripts.cards.SV1.Pokgear30_186 import pokegear_3_0


card = ItemCardDef(
    guid="307f7f44-275a-52a2-8f2e-300fd37739e1",
    key="SWSH1",
    name="com.direwolfdigital.cake.data.archetypes.trainer.Pokgear30.Name",
    display_name="Pokégear 3.0",
    searchable_by=["Pokégear 3.0", "Item"],
    subtypes=["Item"],
    collector_number=174,
    set_code="SWSH1",
    rarity=Rarities.Uncommon,
    effect=pokegear_3_0,
)
