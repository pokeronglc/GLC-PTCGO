from spirit.game.data_utils import PokemonToolCardDef, Ability, Triggers
from spirit.game.attributes import Rarities, PokemonTypes, SpecialConditions, AttrID
from spirit.game.card_effects.passives_common import is_in_active_spot
from spirit.game.card_effects.standard_era import standard_passive


async def _burning_scarf_trigger(ctx):
    # The granted Ability's source can be the Tool card itself; the Fire
    # check belongs to the Pokémon it's attached to.
    from spirit.game.models.board import PokemonEntity
    pokemon = ctx.source
    if not isinstance(pokemon, PokemonEntity):
        pokemon = getattr(pokemon, "parent", None)
    if pokemon is None or ctx.damaged_by is None:
        return
    from spirit.game.session.passives import effective_pokemon_types
    if PokemonTypes.FIRE.value not in effective_pokemon_types(ctx.board, pokemon) \
            or not is_in_active_spot(pokemon):
        return
    await ctx.apply_special_condition(ctx.damaged_by, SpecialConditions.BURNED)


card = PokemonToolCardDef(
    guid="1c9666f9-be63-52b0-bd4e-ca7d86810e73",
    key="SWSH2",
    name="com.direwolfdigital.cake.data.archetypes.trainer.BurningScarf.Name",
    display_name="Burning Scarf",
    searchable_by=["Burning Scarf", "Pokémon Tool"],
    subtypes=["Pok\u00e9mon Tool"],
    collector_number=155,
    set_code="SWSH2",
    rarity=Rarities.Uncommon,
    passive=standard_passive("If the Fire Pokémon this card is attached to is in the Active Spot and is damaged by an opponent's attack (even if it is Knocked Out), the Attacking Pokémon is now Burned."),
)
