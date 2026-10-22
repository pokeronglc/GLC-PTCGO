from spirit.game.data_utils import FossilItemCardDef, Ability, Triggers
from spirit.game.card_effects.trainers import FossilBodyPassive, fossil_discard_ability
from spirit.game.attributes import PokemonTypes, Rarities
from spirit.game.card_effects.standard_era import (
    standard_ability, standard_attack, standard_passive, standard_stadium_ability,
    standard_trainer_effect,
)


card = FossilItemCardDef(
    guid="d7c7fd29-8a46-51c4-8132-5d3334ed7de7",
    key="RSV10PT5",
    name="com.direwolfdigital.cake.data.archetypes.trainer.AntiquePlumeFossil.Name",
    display_name="Antique Plume Fossil",
    searchable_by=["Antique Plume Fossil", "Item", "AntiquePlumeFossil"],
    subtypes=["Item"],
    collector_number=79,
    set_code="RSV10PT5",
    regulation_mark="I",
    rarity=Rarities.Common,
    hp=60,
    passive=FossilBodyPassive(blocks_conditions=True),
    abilities=[
        fossil_discard_ability(),
        Ability(
            title="Plume Protection",
            game_text="As long as this Pokémon is on your Bench, prevent all damage done to this Pokémon by attacks from your opponent's Pokémon.",
            passive=standard_passive("As long as this Pokémon is on your Bench, prevent all damage done to this Pokémon by attacks from your opponent's Pokémon."),
        ),
    ],
)
