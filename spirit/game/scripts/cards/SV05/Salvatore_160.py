from spirit.game.data_utils import SupporterCardDef
from spirit.game.attributes import PokemonTypes, Rarities
from spirit.game.card_effects.trainer_followup import salvatore, salvatore_condition
from spirit.game.card_effects.standard_era import (
    standard_attack, standard_passive, standard_stadium_ability,
    standard_trainer_effect,
)


card = SupporterCardDef(
    guid="08853f0b-d6af-56c8-bd9e-a5406da851c9",
    key="SV05",
    name="com.direwolfdigital.cake.data.archetypes.trainer.Salvatore.Name",
    display_name="Salvatore",
    searchable_by=["Salvatore", "Supporter", "Salvatore"],
    subtypes=["Supporter"],
    collector_number=160,
    set_code="SV05",
    regulation_mark="H",
    rarity=Rarities.Uncommon,
    effect=salvatore,
    condition=salvatore_condition,
)
