from spirit.game.data_utils import ItemCardDef
from spirit.game.attributes import AttrID, PokemonTypes, Rarities
from spirit.game.card_effects.passives_common import takes_less_passive


def _metal_teammate_of(player_id):
    def protects(target, carrier):
        if target.owning_player_id != player_id:
            return False
        types = target.get_attribute(AttrID.POKEMON_TYPES) or []
        return PokemonTypes.METAL.value in types
    return protects


async def iron_defender(ctx):
    """During your opponent's next turn, all of your Metal Pokémon take 30
    less damage from attacks (including new Pokémon that come into play)."""
    shield = takes_less_passive(
        30, protects=_metal_teammate_of(ctx.player_id), stack_key="Iron Defender",
    )
    # Side-wide, not carried by today's Pokémon: newcomers are covered even
    # after every Pokémon that was in play has left.
    ctx.add_temporary_player_passive(
        ctx.player_id, shield, ctx.session.turn_state.turn_number + 1)


card = ItemCardDef(
    guid="ad66af6d-0758-5cb9-a2b8-bfdc4ceb73b4",
    key="ME1",
    name="com.direwolfdigital.cake.data.archetypes.trainer.IronDefender.Name",
    display_name="Iron Defender",
    searchable_by=["Iron Defender","Item","IronDefender"],
    subtypes=["Item"],
    collector_number=118,
    set_code="ME1",
    regulation_mark="I",
    rarity=Rarities.Uncommon,
    effect=iron_defender,
)
