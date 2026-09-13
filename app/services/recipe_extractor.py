import json
import re

from anthropic import Anthropic

from app.config import settings

SYSTEM_PROMPT = (
    "You turn spoken-word transcripts of cooking videos into clean, structured "
    "recipes. Respond with ONLY a JSON object, no prose, no markdown code "
    "fences, matching exactly this shape: "
    '{"title": string, "servings": string or null, "total_time": string or '
    'null, "ingredients": [string, ...], "steps": [string, ...]}. '
    "Write ingredients as one item per line with quantities when they're "
    "stated or clearly implied. Write steps as short, clear imperative "
    "sentences in the order they should be done, filling in obvious gaps "
    "(e.g. preheat oven) a home cook would expect. If the transcript doesn't "
    "actually describe a recipe, set title to \"Not a recipe\" and return "
    "empty ingredients and steps lists."
)


def _client() -> Anthropic:
    return Anthropic(api_key=settings.anthropic_api_key)


def extract_recipe(transcript: str) -> dict:
    message = _client().messages.create(
        model=settings.anthropic_model,
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": f"Transcript:\n\n{transcript}"}],
    )
    text = "".join(block.text for block in message.content if block.type == "text").strip()
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.MULTILINE).strip()
    return json.loads(text)
