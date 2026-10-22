from spirit.game.data_utils import ItemCardDef
from spirit.game.attributes import Rarities
# Same text as Level Ball 129: share its effect so every printing behaves alike.
from spirit.game.scripts.cards.SWSH5.LevelBall_129 import card as _shared


card = ItemCardDef(
    guid="311e4f3c-068f-589e-962c-530d05d4a0f1",
    key="SWSH5",
    name="com.direwolfdigital.cake.data.archetypes.trainer.LevelBall.Name",
    display_name="Level Ball",
    searchable_by=["Level Ball", "Item"],
    subtypes=["Item"],
    collector_number=181,
    set_code="SWSH5",
    rarity=Rarities.RareSecret,
    effect=_shared.effect,
)
