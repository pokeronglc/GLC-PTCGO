from spirit.game.data_utils import FossilItemCardDef, Ability, Triggers
from spirit.game.card_effects.trainers import FossilBodyPassive, fossil_discard_ability
from spirit.game.attributes import PokemonTypes, Rarities
from spirit.game.card_effects.standard_era import (
    standard_ability, standard_attack, standard_passive, standard_stadium_ability,
    standard_trainer_effect,
)


card = FossilItemCardDef(
    guid="a46e2788-672b-515f-838e-296ebce9f735",
    key="ME5",
    name="com.direwolfdigital.cake.data.archetypes.trainer.AntiqueSkullFossil.Name",
    display_name="Antique Skull Fossil",
    searchable_by=["Antique Skull Fossil", "Item", "AntiqueSkullFossil"],
    subtypes=["Item"],
    collector_number=73,
    set_code="ME5",
    regulation_mark="J",
    rarity=Rarities.Common,
    hp=60,
    passive=FossilBodyPassive(blocks_conditions=True),
    abilities=[
        fossil_discard_ability(),
        Ability(
            title="Spiny Skull",
            game_text="If this Pokémon is in the Active Spot and is damaged by an attack from your opponent's Pokémon (even if this Pokémon is Knocked Out), put 3 damage counters on the Attacking Pokémon.",
            effect=standard_ability,
            trigger=Triggers.ON_DAMAGED_BY_ATTACK,
        ),
    ],
)
