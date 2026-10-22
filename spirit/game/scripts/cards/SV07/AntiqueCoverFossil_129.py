from spirit.game.data_utils import FossilItemCardDef, Ability, Triggers
from spirit.game.card_effects.trainers import FossilBodyPassive, fossil_discard_ability
from spirit.game.attributes import PokemonTypes, Rarities
from spirit.game.card_effects.standard_era import (
    standard_ability, standard_attack, standard_passive, standard_stadium_ability,
    standard_trainer_effect,
)


card = FossilItemCardDef(
    guid="776f60a3-b390-5f43-a75b-742e47f8aed9",
    key="SV07",
    name="com.direwolfdigital.cake.data.archetypes.trainer.AntiqueCoverFossil.Name",
    display_name="Antique Cover Fossil",
    searchable_by=["Antique Cover Fossil", "Item", "AntiqueCoverFossil"],
    subtypes=["Item"],
    collector_number=129,
    set_code="SV07",
    regulation_mark="H",
    rarity=Rarities.Common,
    hp=60,
    passive=FossilBodyPassive(blocks_conditions=True),
    abilities=[
        fossil_discard_ability(),
        Ability(
            title="Protective Cover",
            game_text="Prevent all effects of attacks used by your opponent's Pokémon done to this Pokémon. (Damage is not an effect.)",
            passive=standard_passive("Prevent all effects of attacks used by your opponent's Pokémon done to this Pokémon. (Damage is not an effect.)"),
        ),
    ],
)
