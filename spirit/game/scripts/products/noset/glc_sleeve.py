from spirit.game.data_utils import SleeveDef

# Gym Leader Challenge card back.  The client draws the Basic Sleeve from its
# own built-in art, so a server-side image swap can't reach it; this is a
# separate sleeve whose art (glc_sleeve.png in assets/products/custom_sleeves)
# is appended to the cardSleeves bundle.  Matches swap Basic Sleeve for it --
# see GLC_SLEEVE_GUID in spirit/game/starter_content.py.
product = SleeveDef(
    guid="34658635-a8af-53ad-ba94-649961eea40f",
    key="NoSet",
    name="Gym Leader Challenge Sleeve",
    image_url="glc_sleeve"
)
