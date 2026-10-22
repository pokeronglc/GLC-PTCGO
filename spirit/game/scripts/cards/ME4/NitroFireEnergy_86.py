from spirit.game.data_utils import EnergyCardDef
from spirit.game.attributes import PokemonTypes, Rarities
from spirit.game.card_effects.standard_era import energy_on_attach, standard_passive
from spirit.game.session.passives import effective_pokemon_types


async def nitro_return_to_hand(ctx, energy, pokemon):
    """Discarded by an effect of its Fire carrier's attack: put it into
    the hand after attack damage and effects (deferred_actions)."""
    if pokemon is None or energy not in ctx.discard_pile(energy.owning_player_id):
        return
    if PokemonTypes.FIRE.value not in effective_pokemon_types(ctx.board, pokemon):
        return
    await ctx.put_in_hand([energy], reveal=True)


card = EnergyCardDef(
    guid="f37baa9f-6e68-5ced-b448-25a5c47d7844",
    key="ME4",
    name="Nitro Fire Energy",
    display_name="Nitro Fire Energy",
    searchable_by=["Nitro Fire Energy", "Special", "NitroFireEnergy"],
    subtypes=["Special"],
    collector_number=86,
    set_code="ME4",
    regulation_mark="J",
    rarity=Rarities.Rare,
    energy_type=PokemonTypes.FIRE,
    is_special=True,
    outside_play_types=[],
    provides=[[PokemonTypes.FIRE]],
    on_discarded_by_carrier_attack=nitro_return_to_hand,
    passive=standard_passive("As long as this card is attached to a Pokémon, it provides Fire Energy.\n \nIf this card is discarded by an effect of an attack used by the Fire Pokémon this card is attached to, put this card into your hand after attack damage and effects."),
)
