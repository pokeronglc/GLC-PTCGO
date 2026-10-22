from spirit.game.data_utils import SupporterCardDef
from spirit.game.attributes import Rarities
from spirit.game.card_effects.support_common import draw_until_effect

card = SupporterCardDef(
    guid="c4a24f69-9880-5315-bbbf-df00cbd566f4",
    key="SWSH5",
    name="com.direwolfdigital.cake.data.archetypes.trainer.KorrinasFocus.Name",
    display_name="Korrina's Focus",
    searchable_by=["Korrina's Focus", "Supporter", "Rapid Strike"],
    subtypes=["Supporter", "Rapid Strike"],  # same card as 128/174 (Rapid Strike); source data mislabeled the full art
    collector_number=160,
    set_code="SWSH5",
    rarity=Rarities.RareUltra,
    effect=draw_until_effect(6)
)
