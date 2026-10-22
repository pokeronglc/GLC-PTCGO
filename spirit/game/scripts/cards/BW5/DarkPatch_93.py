from spirit.game.data_utils import ItemCardDef
from spirit.game.attributes import Rarities
# Same text as Dark Patch ASR 139 (tested): share its effect and play
# condition so every printing behaves alike.
from spirit.game.scripts.cards.SWSH10.DarkPatch_139 import card as _shared

card = ItemCardDef(
    guid="c44bc391-e593-5306-890a-219ff24b55e3",
    key="BW5",
    name="com.direwolfdigital.cake.data.archetypes.trainer.DarkPatch.Name",
    display_name="Dark Patch",
    searchable_by=["Dark Patch","Item","DarkPatch"],
    subtypes=["Item"],
    collector_number=93,
    set_code="BW5",
    rarity=Rarities.Uncommon,
    effect=_shared.effect,
    condition=_shared.condition,
)
