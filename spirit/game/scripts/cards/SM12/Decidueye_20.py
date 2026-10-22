from spirit.game.data_utils import Attack, Ability, PokemonCardDef, Activations, Triggers
from spirit.game.attributes import AttrID, PokemonTypes, PokemonStage, Rarities
from spirit.game.card_effects.standard_era import (
    standard_ability, standard_attack, standard_passive,
)



async def tracking_shot(ctx):
    """RULING (owner, Oct 14): 80 to the opponent's Active, and ALSO 80 to 1
    of their Benched Pokémon that already has damage counters on it (no
    Weakness/Resistance on the Bench). Not optional when a target exists."""
    damaged = [p for p in ctx.opponent_bench()
               if p.get_attribute(AttrID.HP, 0) < ctx.max_hp(p)]
    await ctx.deal_damage(80)
    damaged = [p for p in damaged if ctx.pokemon_is_in_play(p)]
    if not damaged:
        return
    target = await ctx.choose_pokemon(
        damaged, "Choose 1 of your opponent's damaged Benched Pokémon")
    if target is None:
        target = damaged[0]
    await ctx.deal_damage(80, target=target, apply_modifiers=False)


card = PokemonCardDef(
    guid='e757cef4-abc6-5a3d-9e62-3e021f67e56a',
    key='SM12',
    name='com.direwolfdigital.cake.data.archetypes.pokemon.Decidueye.Name',
    display_name='Decidueye',
    searchable_by=['Decidueye', 'Stage 2', 'Decidueye'],
    subtypes=['Stage 2'],
    collector_number=20,
    set_code='SM12',
    regulation_mark=None,
    rarity=Rarities.RareHolo,
    hp=140,
    elements=[PokemonTypes.GRASS],
    stage=PokemonStage.STAGE2,
    retreat_cost=1,
    weakness_type=PokemonTypes.FIRE,
    weakness_amount=2,
    evolves_from='com.direwolfdigital.cake.data.archetypes.pokemon.Dartrix.Name',
    family_id=722,
    abilities=[
        Attack(
            title='Skill Dive',
            game_text="This attack does 40 damage to 1 of your opponent's Pokémon. (Don't apply Weakness and Resistance for Benched Pokémon.)",
            cost={PokemonTypes.GRASS: 1},
            effect=standard_attack,
        ),
        Attack(
            title='Tracking Shot',
            game_text="This attack does 80 damage to 1 of your opponent's Benched Pokémon that has any damage counters on it. (Don't apply Weakness and Resistance for Benched Pokémon.)",
            cost={PokemonTypes.COLORLESS: 2},
            damage=80,
            effect=tracking_shot,
        ),
    ],
)
