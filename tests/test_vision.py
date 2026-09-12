import json
import pytest
from alcana_bot.vision import extract_dimensions_from_image, extract_letter_spec_from_image, ExtractionError

class FakeTextBlock:
    def __init__(self, text):
        self.text = text

class FakeResponse:
    def __init__(self, text):
        self.content = [FakeTextBlock(text)]

class FakeMessages:
    def __init__(self, response_text):
        self._response_text = response_text
    def create(self, **kwargs):
        return FakeResponse(self._response_text)

class FakeClient:
    def __init__(self, response_text):
        self.messages = FakeMessages(response_text)

def test_extract_dimensions_from_image_parses_valid_json():
    client = FakeClient(json.dumps({"width_cm": 680, "height_cm": 80, "confidence": 0.95}))
    result = extract_dimensions_from_image(client, image_bytes=b"fake", media_type="image/png")
    assert result == {"width_cm": 680, "height_cm": 80, "confidence": 0.95}

def test_extract_dimensions_from_image_low_confidence_raises():
    client = FakeClient(json.dumps({"width_cm": 680, "height_cm": 80, "confidence": 0.3}))
    with pytest.raises(ExtractionError, match="confidence"):
        extract_dimensions_from_image(client, image_bytes=b"fake", media_type="image/png")

def test_extract_dimensions_from_image_malformed_response_raises():
    client = FakeClient("not json at all")
    with pytest.raises(ExtractionError, match="parse"):
        extract_dimensions_from_image(client, image_bytes=b"fake", media_type="image/png")

def test_extract_letter_spec_from_image_parses_valid_json():
    client = FakeClient(json.dumps({"letter_count": 6, "height_cm": 80, "confidence": 0.9}))
    result = extract_letter_spec_from_image(client, image_bytes=b"fake", media_type="image/png")
    assert result == {"letter_count": 6, "height_cm": 80, "confidence": 0.9}
