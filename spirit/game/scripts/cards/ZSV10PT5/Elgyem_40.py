from spirit.game.data_utils import PokemonCardDef, Attack, Ability
from spirit.game.attributes import PokemonStage, PokemonTypes, Rarities
from spirit.game.card_effects.attacks_common import count_energy, damage_per

async def energy_warp(ctx):
    """Move an Energy from 1 of your opponent's Pokémon to another of their Pokémon."""
    pokemon = list(ctx.opponent_pokemon_in_play())
    sources = [p for p in pokemon if ctx.attached_energies(p)]
    if len(pokemon) < 2 or not sources:
        return
    source = await ctx.choose_pokemon(
        sources, "Choose 1 of your opponent's Pokémon to move an Energy from")
    if source is None or ctx.effects_blocked(source):
        return
    energies = ctx.attached_energies(source)
    energy = energies[0]
    if len(energies) > 1:
        picked = await ctx.choose_cards(energies, 1, prompt="Choose an Energy to move")
        if not picked:
            return
        energy = picked[0]
    dest = await ctx.choose_pokemon(
        [p for p in pokemon if p is not source],
        "Choose a Pokémon to receive the Energy")
    if dest is not None:
        await ctx.move_energy(energy, dest)


card = PokemonCardDef(
    guid="e4d0ced3-688f-5d0a-88d3-3e14cd150e1a",
    key="ZSV10PT5",
    name="com.direwolfdigital.cake.data.archetypes.pokemon.Elgyem.Name",
    display_name="Elgyem",
    searchable_by=["Elgyem","Basic","Elgyem"],
    subtypes=["Basic"],
    collector_number=40,
    set_code="ZSV10PT5",
    regulation_mark="I",
    rarity=Rarities.Common,
    hp=60,
    elements=[PokemonTypes.PSYCHIC],
    stage=PokemonStage.BASIC,
    retreat_cost=1,
    weakness_type=PokemonTypes.DARKNESS,
    resistance_type=PokemonTypes.FIGHTING,
    family_id=605,
    abilities=[
        Attack(
            title="Slight Shift",
            game_text="Move an Energy from 1 of your opponent's Pokémon to another of their Pokémon.",
            cost={PokemonTypes.PSYCHIC: 1},
            effect=energy_warp,
        ),
        Attack(
            title="Beam",
            cost={PokemonTypes.COLORLESS: 3},
            damage=40,
        ),
    ],
)
