import os
import re
import subprocess
import defusedxml.ElementTree as ET

class CdrExtractionError(Exception):
    pass

_UNIT_TO_CM = {
    "mm": 0.1,
    "cm": 1.0,
    "in": 2.54,
    "pt": 2.54 / 72,
    "px": 2.54 / 96,  # assume 96dpi, matches LibreOffice's SVG export default
}

def _to_cm(value_str: str) -> float:
    match = re.match(r"^([\d.]+)([a-z%]*)$", value_str.strip())
    if not match:
        raise CdrExtractionError(f"Could not parse SVG dimension: '{value_str}'")
    number, unit = match.groups()
    unit = unit or "px"
    if unit not in _UNIT_TO_CM:
        raise CdrExtractionError(f"Unsupported SVG unit: '{unit}'")
    return float(number) * _UNIT_TO_CM[unit]

def parse_svg_page_size(svg_content: str) -> tuple[float, float]:
    root = ET.fromstring(svg_content)
    width = root.get("width")
    height = root.get("height")
    if not width or not height:
        raise CdrExtractionError("SVG root element is missing width/height attributes")
    return _to_cm(width), _to_cm(height)

def convert_cdr_to_svg(cdr_path: str, soffice_path: str, output_dir: str) -> str:
    result = subprocess.run(
        [soffice_path, "--headless", "--convert-to", "svg", "--outdir", output_dir, cdr_path],
        capture_output=True, text=True, timeout=60,
    )
    if result.returncode != 0:
        raise CdrExtractionError(f"soffice conversion failed: {result.stderr}")
    base_name = os.path.splitext(os.path.basename(cdr_path))[0]
    svg_path = os.path.join(output_dir, f"{base_name}.svg")
    if not os.path.exists(svg_path):
        raise CdrExtractionError(f"Expected output SVG not found: {svg_path}")
    return svg_path

def extract_cdr_dimensions(cdr_path: str, soffice_path: str) -> tuple[float, float]:
    import tempfile
    with tempfile.TemporaryDirectory() as tmp_dir:
        svg_path = convert_cdr_to_svg(cdr_path, soffice_path, tmp_dir)
        with open(svg_path, "r", encoding="utf-8") as f:
            svg_content = f.read()
        return parse_svg_page_size(svg_content)
