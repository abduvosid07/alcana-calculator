import json
from google.genai import types

class ExtractionError(Exception):
    pass

MODEL = "gemini-3.6-flash"
CONFIDENCE_THRESHOLD = 0.6

_DIMENSIONS_PROMPT = (
    "This image shows an advertising design with printed dimension labels "
    "(e.g. numbers with 'см' or 'cm'). Read the overall width and height in "
    "centimeters. Reply with ONLY a JSON object, no other text, in this exact "
    'shape: {"width_cm": <number>, "height_cm": <number>, "confidence": <0-1>}. '
    "Set confidence low (below 0.5) if the labels are unclear or ambiguous."
)

_LETTERS_PROMPT = (
    "This image shows a design for volumetric/3D letters (dimensional signage "
    "letters). The design may also include non-alphabetic symbols, icons, or "
    "logos fabricated the same way as the letters (e.g. a heart, a star, or "
    "another custom shape next to the text) -- count each such symbol as a "
    "unit too, exactly like a letter. The design may contain items at more "
    "than one height (e.g. different words/lines of text, or a symbol at a "
    "different height than the text) -- identify each distinct group of "
    "items (letters and/or symbols) that share the same height. For each "
    "group, count exactly how many individual units need to be fabricated, "
    "and read or infer the height in centimeters (one of 60, 80, 100, or "
    "120cm, or another explicit value). Reply with ONLY a JSON object, no "
    'other text, in this exact shape: {"groups": [{"letter_count": '
    '<integer>, "height_cm": <number>}, ...], "confidence": <0-1>}. Set '
    "confidence low (below 0.5) if any group is unclear."
)

def _strip_code_fence(text: str) -> str:
    # Gemini (unlike Claude) sometimes wraps JSON in a ```json ... ``` block
    # despite being told to reply with only JSON -- strip that if present.
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.strip("`")
        if stripped.startswith("json"):
            stripped = stripped[4:]
    return stripped.strip()

def _call_vision(client, image_bytes: bytes, media_type: str, prompt: str, required_keys: list[str]) -> dict:
    # Broad except on purpose: this is the boundary to an external SDK
    # (network errors, auth errors, rate limits, empty/missing text on the
    # response). Every failure mode here means the same thing to the caller --
    # fall back to manual entry -- so they all become ExtractionError.
    try:
        response = client.models.generate_content(
            model=MODEL,
            contents=[
                types.Part.from_bytes(data=image_bytes, mime_type=media_type),
                prompt,
            ],
        )
        text = response.text
    except Exception as e:
        raise ExtractionError(f"Vision API call failed: {type(e).__name__}: {e}") from e

    if not text:
        raise ExtractionError("Vision API returned an empty response")

    text = _strip_code_fence(text)

    try:
        result = json.loads(text)
    except json.JSONDecodeError as e:
        raise ExtractionError(f"Could not parse model response as JSON: {text!r}") from e

    for key in required_keys:
        if key not in result:
            raise ExtractionError(f"Model response missing required key '{key}': {result}")

    if result["confidence"] < CONFIDENCE_THRESHOLD:
        raise ExtractionError(f"Extraction confidence too low ({result['confidence']}); fall back to manual entry")

    return result

def extract_dimensions_from_image(client, image_bytes: bytes, media_type: str) -> dict:
    return _call_vision(client, image_bytes, media_type, _DIMENSIONS_PROMPT, ["width_cm", "height_cm", "confidence"])

def extract_letter_spec_from_image(client, image_bytes: bytes, media_type: str) -> dict:
    result = _call_vision(client, image_bytes, media_type, _LETTERS_PROMPT, ["groups", "confidence"])
    groups = result["groups"]
    if not isinstance(groups, list) or not groups:
        raise ExtractionError(f"Model response 'groups' must be a non-empty list: {result}")
    for group in groups:
        if "letter_count" not in group or "height_cm" not in group:
            raise ExtractionError(f"Model response has a malformed entry in 'groups' (missing letter_count/height_cm): {result}")
    return result
