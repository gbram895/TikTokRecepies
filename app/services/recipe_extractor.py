"""Turn a transcript + caption into a structured recipe using plain text
heuristics (regex/keyword matching) only -- no paid AI API calls, no
network access, runs instantly and for free.

It won't be as sharp as an LLM on messy narration, but it works well when
the video either (a) has a clearly-spoken ingredient list ("two cups of
flour", "a pinch of salt") and imperative steps ("preheat the oven", "mix
it together"), or (b) has a caption that already spells out an
Ingredients:/Instructions: list, which a lot of recipe TikToks do.
"""

import re

_NUM = (
    r'(?:\d+(?:\.\d+)?(?:\s*/\s*\d+)?|\d+\s*-\s*\d+|a|an|one|two|three|four|'
    r'five|six|seven|eight|nine|ten|half(?:\s+a)?|quarter(?:\s+a)?|'
    r'couple(?:\s+of)?|few)'
)

_UNITS = (
    r'cups?|tbsps?|tablespoons?|tsps?|teaspoons?|ounces?|oz|lbs?|pounds?|'
    r'grams?|g|kilograms?|kg|milliliters?|ml|liters?|l|cloves?|pinch(?:es)?|'
    r'dash(?:es)?|cans?|slices?|pieces?|handfuls?|sticks?|bunche?s?|sprigs?|'
    r'splash(?:es)?|drizzles?'
)

_COMMON_FOODS = (
    r'eggs?|onions?|garlic|salt|pepper|sugar|flour|butter|oil|milk|cheese|'
    r'chicken|beef|pork|bacon|rice|pasta|noodles?|tomato(?:es)?|potato(?:es)?|'
    r'cream|vanilla|water|lemons?|limes?|honey|syrup|chocolate|vinegar|'
    r'spinach|carrots?|celery|mushrooms?|shrimp|fish|beans?|corn|avocado(?:s)?|'
    r'yogurt|broth|stock|wine|cilantro|parsley|basil|oregano|cinnamon|'
    r'paprika|cumin|ginger|scallions?|shallots?|breadcrumbs?|tortillas?|bread'
)

# Stop the phrase capture at punctuation or a connector word, so
# "two tablespoons of olive oil in a pan" doesn't swallow "in a pan", and
# don't let the extra-word group itself swallow a connector before that
# lookahead gets a chance to fire.
_CONNECTORS = r'and|with|for|in|on|into|over'
_PHRASE_STOP = rf'(?=[,.;!?]|$| (?:{_CONNECTORS}) )'
_EXTRA_WORD = rf'(?:\s+(?!(?:{_CONNECTORS})\b)[a-z][\w\-]*)'

_INGREDIENT_PHRASE_RE = re.compile(
    rf'\b{_NUM}\s+(?:{_UNITS})\s+(?:of\s+)?[a-z][\w\-]*{_EXTRA_WORD}{{0,3}}{_PHRASE_STOP}'
    r'|'
    rf'\b(?:pinch|dash|handful|splash|drizzle|bit)\s+of\s+[a-z][\w\-]*{_EXTRA_WORD}{{0,3}}{_PHRASE_STOP}'
    r'|'
    rf'\b{_NUM}\s+(?:{_COMMON_FOODS})\b',
    re.IGNORECASE,
)

_ACTION_VERBS = [
    "add", "mix", "stir", "bake", "chop", "heat", "pour", "whisk", "preheat",
    "simmer", "boil", "fry", "season", "serve", "cook", "place", "cut",
    "slice", "dice", "mince", "combine", "blend", "whip", "fold", "spread",
    "drizzle", "sprinkle", "cover", "remove", "transfer", "flip", "grate",
    "peel", "mash", "knead", "roll", "bring", "reduce", "garnish", "top",
    "layer", "marinate", "rest", "chill", "freeze", "melt", "saute",
    "sauté", "toss", "coat", "dip", "spray", "grease", "line", "crack",
    "beat", "wash", "rinse", "drain", "preheat", "let",
]
_ACTION_VERB_GROUP = "(?:" + "|".join(_ACTION_VERBS) + r")(?:e?d|e?s|ing)?\b"
ACTION_VERB_RE = re.compile(r'\b' + _ACTION_VERB_GROUP, re.IGNORECASE)
_ACTION_VERB_START_RE = re.compile(r'^' + _ACTION_VERB_GROUP, re.IGNORECASE)

_LEADING_FILLER_RE = re.compile(
    r"^(?:first|second|third|next|then|now|finally|meanwhile|so|okay|"
    r"alright|and|also|after that|once (?:that'?s |it'?s )?(?:done|ready))"
    r"[,]?\s+",
    re.IGNORECASE,
)

_TITLE_PATTERNS = [
    re.compile(r'how to make (?:a |an |the )?(.+?)(?:[.!,]|$)', re.IGNORECASE),
    re.compile(
        r"(?:today|so today)?[, ]*(?:we'?re|i'?m) making (?:a |an |the )?(.+?)(?:[.!,]|$)",
        re.IGNORECASE,
    ),
    re.compile(r'recipe for (?:a |an |the )?(.+?)(?:[.!,]|$)', re.IGNORECASE),
    re.compile(r"this is (?:my |the )(.+?) recipe", re.IGNORECASE),
]

SERVINGS_RE = re.compile(r'\bserves?\s+(\d+)\b|\b(\d+)\s+servings?\b', re.IGNORECASE)
TIME_RE = re.compile(r'\b(\d+)\s*(minutes?|mins?|hours?|hrs?)\b', re.IGNORECASE)

_INGREDIENTS_HEADER_RE = re.compile(
    r'^(ingredients?|what you.?ll need|you.?ll need)\s*[:\-]?\s*$', re.IGNORECASE
)
_STEPS_HEADER_RE = re.compile(
    r'^(instructions?|directions?|method|steps|how to make it)\s*[:\-]?\s*$',
    re.IGNORECASE,
)


def _clean(text: str) -> str:
    return re.sub(r'\s+', ' ', text or '').strip()


def _split_clauses(text: str) -> list[str]:
    text = re.sub(r'\s+', ' ', text).strip()
    parts = re.split(r'(?<=[.!?])\s+|;\s+', text)
    return [p.strip(" .,-•*—") for p in parts if p.strip(" .,-•*—")]


def _capitalize(clause: str) -> str:
    return clause[:1].upper() + clause[1:] if clause else clause


def _parse_sectioned(text: str) -> tuple[list[str], list[str]]:
    """Pull explicit "Ingredients:" / "Instructions:" sections out of a
    TikTok caption, when the creator already wrote the recipe out."""
    ingredients: list[str] = []
    steps: list[str] = []
    section = None
    for raw_line in (text or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        bare = line.strip("-•*— ").strip()
        if _INGREDIENTS_HEADER_RE.match(bare):
            section = "ingredients"
            continue
        if _STEPS_HEADER_RE.match(bare):
            section = "steps"
            continue
        if section is None:
            continue
        bullet_match = re.match(r'^[-•*]\s*(.+)$', line) or re.match(r'^\d+[.)]\s*(.+)$', line)
        item = bullet_match.group(1).strip() if bullet_match else bare
        if not item:
            continue
        (ingredients if section == "ingredients" else steps).append(item)
    return ingredients, steps


def _extract_steps(text: str) -> list[str]:
    steps: list[str] = []
    for clause in _split_clauses(text):
        stripped = _LEADING_FILLER_RE.sub('', clause).strip()
        # allow a couple of rounds of filler-stripping ("and then add...")
        stripped = _LEADING_FILLER_RE.sub('', stripped).strip()
        if _ACTION_VERB_START_RE.match(stripped) or ACTION_VERB_RE.search(clause):
            steps.append(_capitalize(clause))
    return steps


def _extract_ingredient_phrases(text: str) -> list[str]:
    seen: dict[str, str] = {}
    for match in _INGREDIENT_PHRASE_RE.finditer(text):
        phrase = re.sub(r'\s+', ' ', match.group(0)).strip(" .,-")
        key = phrase.lower()
        if key not in seen:
            seen[key] = _capitalize(phrase)
    return list(seen.values())


def _guess_title(transcript: str, video_title: str) -> str:
    for pattern in _TITLE_PATTERNS:
        match = pattern.search(transcript)
        if match:
            candidate = match.group(1).strip(" .,!")
            if 2 <= len(candidate) <= 60:
                return candidate.title()
    if video_title:
        # TikTok captions are often "Title! #hashtag #hashtag emoji-soup" --
        # keep just the first clause and drop hashtags/emoji clutter.
        first_clause = re.split(r'[.!\n]', video_title)[0]
        first_clause = re.sub(r'#\w+', '', first_clause).strip(" -–|")
        if 2 <= len(first_clause) <= 80:
            return first_clause
    return "Recipe from TikTok"


def extract_recipe(transcript: str, description: str = "", video_title: str = "") -> dict:
    """Build {"title", "servings", "total_time", "ingredients", "steps"}
    from a spoken-word transcript and/or the video's caption, using only
    regex/keyword heuristics."""
    sect_ingredients, sect_steps = _parse_sectioned(description or "")

    transcript = _clean(transcript)
    description = _clean(description)
    combined = f"{description} {transcript}".strip()

    ingredients = sect_ingredients or _extract_ingredient_phrases(combined)
    steps = sect_steps or _extract_steps(combined)

    servings_match = SERVINGS_RE.search(combined)
    servings = None
    if servings_match:
        servings = next((g for g in servings_match.groups() if g), None)

    time_match = TIME_RE.search(combined)
    total_time = f"{time_match.group(1)} {time_match.group(2)}" if time_match else None

    return {
        "title": _guess_title(transcript, video_title),
        "servings": servings,
        "total_time": total_time,
        "ingredients": ingredients,
        "steps": steps,
    }
