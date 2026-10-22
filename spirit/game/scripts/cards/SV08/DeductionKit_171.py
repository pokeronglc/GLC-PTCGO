from spirit.game.data_utils import ItemCardDef
from spirit.game.card_effects.trainers import deduction_kit
from spirit.game.attributes import PokemonTypes, Rarities
from spirit.game.card_effects.standard_era import (
    standard_attack, standard_passive, standard_stadium_ability,
    standard_trainer_effect,
)


card = ItemCardDef(
    guid="19a5a6e2-2952-5b1d-8aff-26ac0780df26",
    key="SV08",
    name="com.direwolfdigital.cake.data.archetypes.trainer.DeductionKit.Name",
    display_name="Deduction Kit",
    searchable_by=["Deduction Kit", "Item", "DeductionKit"],
    subtypes=["Item"],
    collector_number=171,
    set_code="SV08",
    regulation_mark="H",
    rarity=Rarities.Uncommon,
    effect=deduction_kit,
)
