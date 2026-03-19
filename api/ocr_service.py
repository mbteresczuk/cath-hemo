"""
Claude Vision OCR for cardiac cath hemodynamic sheets.

Converts a photo of a handwritten or printed cath sheet into
parser-compatible text (one location per line, same format as
parse_hemodynamics() expects).
"""
import base64
import io
import os

import anthropic
from PIL import Image

OCR_PROMPT = """You are extracting hemodynamic measurements from a cardiac catheterization lab data sheet.

The sheet may be handwritten or printed. It may contain values for any of these locations:
SVC, IVC, RA, RV, MPA, RPA, LPA, RPCWP, LPCWP, LA, LV, Aorta

Each location may have:
- An oxygen saturation percentage (a number 40–100, sometimes written with %)
- Pressures: systolic/diastolic, sometimes followed by a mean
- A mean pressure alone (e.g. "m12" or "mean 12")

Output ONLY a plain text block, one location per line, in this exact format:
  LOCATION  saturation  systolic/diastolic  mean

Rules:
1. Use ONLY these exact location names: SVC IVC RA RV MPA RPA LPA RPCWP LPCWP LA LV Aorta
2. Omit any field that is not clearly written on the sheet for that location
3. Write mean as a bare number at the end of the line (e.g. "RA 75 10/8 9")
4. No units, no labels, no punctuation, no blank lines
5. Do NOT guess or infer values that are not clearly visible
6. If a location appears multiple times (e.g. pullback), use the last value
7. If you cannot read a value confidently, omit it

Example output:
SVC 79
IVC 81
RA 75 10/8 9
RV 75 50/5
MPA 75 50/30 38
RPCWP 12
LV 98 95/10
Aorta 98 95/55 72

Now extract the values from the image:"""


_MAX_BYTES = 4_800_000   # stay comfortably under the 5 MB API limit


def _compress_to_limit(image_bytes: bytes) -> tuple[bytes, str]:
    """
    Compress/resize image bytes so they stay under _MAX_BYTES.

    Returns (compressed_bytes, "image/jpeg").
    Strategy:
      1. Try JPEG at decreasing quality levels (85 → 70 → 55 → 40)
      2. If still too large, halve the dimensions and repeat
    """
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")

    for scale in (1.0, 0.75, 0.5, 0.35):
        w = int(img.width * scale)
        h = int(img.height * scale)
        resized = img.resize((w, h), Image.LANCZOS) if scale < 1.0 else img

        for quality in (85, 70, 55, 40):
            buf = io.BytesIO()
            resized.save(buf, format="JPEG", quality=quality, optimize=True)
            data = buf.getvalue()
            if len(data) <= _MAX_BYTES:
                return data, "image/jpeg"

    # Last resort: smallest viable size
    buf = io.BytesIO()
    img.resize((800, int(800 * img.height / img.width)), Image.LANCZOS).save(
        buf, format="JPEG", quality=35, optimize=True
    )
    return buf.getvalue(), "image/jpeg"


def extract_hemo_from_image(image_bytes: bytes, media_type: str = "image/jpeg") -> str:
    """
    Send an image to Claude Vision and return extracted hemodynamic text.

    Returns a string in parser-compatible format, or an empty string on failure.
    Raises ValueError if ANTHROPIC_API_KEY is not set.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY environment variable is not set.")

    client = anthropic.Anthropic(api_key=api_key)

    # Compress if the image exceeds the API's 5 MB base64 limit
    if len(image_bytes) > _MAX_BYTES:
        image_bytes, media_type = _compress_to_limit(image_bytes)

    image_b64 = base64.standard_b64encode(image_bytes).decode("utf-8")

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": image_b64,
                        },
                    },
                    {"type": "text", "text": OCR_PROMPT},
                ],
            }
        ],
    )

    return message.content[0].text.strip()
