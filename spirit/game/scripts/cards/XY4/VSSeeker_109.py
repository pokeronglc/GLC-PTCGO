"""VS Seeker (XY - Phantom Forces 109/119).

  "Put a Supporter card from your discard pile into your hand."

Miracle Headset's shape, with the ACE SPEC generosity dialled back to the
one card this actually gets:

  count=1, minimum=1  a single Supporter, and taking it is mandatory --
                      Miracle Headset is "up to 2" (count=2, minimum=0).
  reveal=True         owner request (Oct 15): the chosen Supporter flashes
                      up for both players and shows in the game log, so
                      the opponent sees what was taken (the discard pile
                      is public anyway; the Japanese print shows it too).
  condition           has_supporter_in_discard gates the play, so the card
                      is not offered with an empty discard.
"""

from spirit.game.data_utils import ItemCardDef
from spirit.game.attributes import Rarities
from spirit.game.card_effects.support_common import recover_from_discard
from spirit.game.card_effects.trainers import has_supporter_in_discard
from spirit.game.session.effects import is_supporter_card

card = ItemCardDef(
    guid="f8bef826-caea-5575-926e-0ffca16f2c5e",
    key="XY4",
    name="com.direwolfdigital.cake.data.archetypes.trainer.VSSeeker.Name",
    display_name="VS Seeker",
    searchable_by=["VS Seeker", "Item", "VSSeeker"],
    subtypes=["Item"],
    collector_number=109,
    set_code="XY4",
    rarity=Rarities.Uncommon,
    effect=recover_from_discard(
        is_supporter_card, count=1, minimum=1, reveal=True, to="hand",
        prompt="Choose a Supporter card to put into your hand.",
    ),
    condition=has_supporter_in_discard,
)
