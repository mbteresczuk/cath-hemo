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
SVC, IVC, RA, RV, MPA, RPA, LPA, RPCWP, LPCWP, pulmonary veins (RUPV/RLPV/LUPV/LLPV), LA, LV, DAo (descending aorta)

Each location may have:
- An oxygen saturation percentage (a number 40–100, sometimes written with %)
- Pressures: systolic/diastolic, sometimes followed by a mean
- A mean pressure alone (e.g. "m12" or "mean 12")

Output TWO blocks in this exact structure — a "Sat" block containing only saturations,
then a "Pressures" block containing only pressures. A location may appear in both blocks.

Sat
  <LOCATION>  <saturation>          (one location per line, saturation only)

Pressures
  <LOCATION>  <systolic/diastolic>  <mean>   (one location per line, pressures only)

Emit the lines WITHIN each block in this order (skip any location with no value on the sheet):

Sat block order:
  SVC, IVC, RA, RV, MPA, RPA, LPA, then each pulmonary vein on its own row
  (RUPV, RLPV, LUPV, LLPV), LA, LV, DAo

Pressures block order:
  SVC, IVC, RA, RV, MPA, RPA, LPA, RPCWP, LPCWP, then each pulmonary vein on its
  own row if a pressure is recorded, LA, LV, DAo

Rules:
1. Use ONLY these exact location names: SVC IVC RA RV MPA RPA LPA RPCWP LPCWP RUPV RLPV LUPV LLPV LA LV DAo
2. Print the literal header line "Sat" before the first block and "Pressures" before the second block.
3. In the Sat block, print ONLY the saturation number (e.g. "RA 75"). No pressures.
4. In the Pressures block, print ONLY pressures (e.g. "RA 6/10 9"). No saturation.
5. Omit any field/line that is not clearly written on the sheet for that location.
6. A lone MEAN pressure (venous locations like SVC/IVC, or the wedges RPCWP/LPCWP)
   must be written with an "m" prefix so it is read as a mean, e.g. "SVC m8", "RPCWP m12".
7. No units, no labels, no punctuation. Keep exactly one blank line between the two blocks.
8. Do NOT guess or infer values that are not clearly visible; if unsure, omit.
9. If a location appears multiple times (e.g. pullback), use the first value.
10. ATRIAL PRESSURES (RA and LA): report as "v/a mean" — V-wave first, A-wave second, then mean.
    - Look for "v" and "a" wave labels on the sheet and output V first, then A.
    - If waves are not labeled, cath sheets typically record the a-wave before the v-wave in time.
      The a-wave is usually the higher of the two values in a normal heart.
      So if you see two unlabeled atrial values, put the lower value first (V) and the higher second (A).
    - Example: sheet shows RA "10/6" or "a=10 v=6" → output "RA 6/10 9" (V=6 first, A=10 second, mean 9).

Example output:
Sat
SVC 79
IVC 81
RA 75
RV 75
MPA 75
RUPV 98
LLPV 98
LA 98
LV 98
DAo 98

Pressures
SVC m8
RA 6/10 9
RV 50/5
MPA 50/30 38
RPCWP m12
LA 5/8 8
LV 95/10
DAo 95/55 72

Now extract the values from the image:"""


# The Anthropic API enforces a 5 MB limit on the base64-encoded image string.
# Base64 expands raw bytes by ~4/3, so the raw byte limit is 5MB * 3/4 ≈ 3.75 MB.
# We use 3.6 MB as a conservative raw-byte threshold to ensure the base64
# output comfortably stays under 5 MB after encoding.
_MAX_RAW_BYTES = 3_600_000   # raw bytes → base64 stays well under 5 MB


def _compress_to_limit(image_bytes: bytes) -> tuple[bytes, str]:
    """
    Compress/resize image bytes so the raw size stays under _MAX_RAW_BYTES
    (ensuring the base64-encoded payload sent to the API stays under 5 MB).

    Strategy: try decreasing JPEG quality levels, then reduce dimensions.
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
            if len(data) <= _MAX_RAW_BYTES:
                return data, "image/jpeg"

    # Last resort: scale down aggressively
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

    # Compress if the raw image would produce a base64 payload > 5 MB.
    # base64 size ≈ raw size * 4/3, so check raw bytes against _MAX_RAW_BYTES.
    if len(image_bytes) > _MAX_RAW_BYTES:
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
