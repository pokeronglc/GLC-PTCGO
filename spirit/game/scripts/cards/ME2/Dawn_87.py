from spirit.game.data_utils import SupporterCardDef
from spirit.game.attributes import Rarities
from spirit.game.session.effects import (
    is_basic_pokemon,
    is_stage1_pokemon,
    is_stage2_pokemon,
)


async def dawn(ctx):
    """Search your deck for a Basic Pokémon, a Stage 1 Pokémon, and a Stage 2
    Pokémon, reveal them, and put them into your hand. Then, shuffle your deck."""
    groups = await ctx.search_deck_groups(
        [(is_basic_pokemon, 1, "A Basic Pokémon"),
         (is_stage1_pokemon, 1, "A Stage 1 Pokémon"),
         (is_stage2_pokemon, 1, "A Stage 2 Pokémon")],
        prompt="Choose a Basic, a Stage 1 and a Stage 2 Pokémon.")
    picks = [card for group in groups for card in group]
    await ctx.put_in_hand(picks, reveal=True)
    await ctx.shuffle_deck()


card = SupporterCardDef(
    guid="cdcb61ab-7c9b-5c5b-abcd-b28d55b971b5",
    key="ME2",
    name="com.direwolfdigital.cake.data.archetypes.trainer.Dawn.Name",
    display_name="Dawn",
    searchable_by=["Dawn", "Supporter", "Dawn"],
    subtypes=["Supporter"],
    collector_number=87,
    set_code="ME2",
    regulation_mark="I",
    rarity=Rarities.Uncommon,
    effect=dawn,
)
