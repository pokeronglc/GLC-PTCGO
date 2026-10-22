from spirit.game.data_utils import StadiumCardDef, Ability, Triggers
from spirit.game.attributes import AttrID, PokemonStage, PokemonTypes, Rarities


async def risky_ruins_watch(ctx):
    """Whenever any player puts a Basic non-Darkness Pokémon onto their Bench
    during their turn, place 2 damage counters on that Pokémon."""
    pokemon = ctx.benched_pokemon
    if pokemon is None:
        return
    types = pokemon.get_attribute(AttrID.POKEMON_TYPES) or []
    if PokemonTypes.DARKNESS.value in types:
        return
    if pokemon.get_attribute(AttrID.STAGE) not in (None, PokemonStage.BASIC.value):
        return
    turn = getattr(getattr(ctx.session, "turn_state", None), "active_player_id", None)
    if turn is not None and pokemon.owning_player_id != turn:
        return          # "during their turn"
    await ctx.deal_damage(20, target=pokemon, apply_modifiers=False,
                          as_counters=True)


card = StadiumCardDef(
    guid="34f2d480-4d64-528e-a379-c5728742136c",
    key="ME1",
    name="com.direwolfdigital.cake.data.archetypes.trainer.RiskyRuins.Name",
    display_name="Risky Ruins",
    searchable_by=["Risky Ruins","Stadium","RiskyRuins"],
    subtypes=["Stadium"],
    collector_number=127,
    set_code="ME1",
    regulation_mark="I",
    rarity=Rarities.Uncommon,
    abilities=[
        Ability(
            title="Risky Ruins",
            game_text="Whenever any player puts a Basic non-Darkness Pokémon onto their Bench during their turn, place 2 damage counters on that Pokémon.",
            trigger=Triggers.ON_POKEMON_BENCHED,
            effect=risky_ruins_watch,
        ),
    ],
)
