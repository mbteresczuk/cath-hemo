#!/bin/bash
# One-time setup for one-click (SAM) masking in the component author.
# LLM auto-tagging needs nothing extra — only this is optional.
#
# Uses MobileSAM (tiny, CPU-friendly ~40 MB) so it runs fine on a laptop.
set -e
cd "$(dirname "$0")"

echo "Installing MobileSAM + torch (CPU)…"
python3 -m pip install --user torch torchvision timm
python3 -m pip install --user git+https://github.com/ChaoningZhang/MobileSAM.git

mkdir -p models
CKPT="models/mobile_sam.pt"
if [ ! -f "$CKPT" ]; then
  echo "Downloading MobileSAM checkpoint…"
  curl -L -o "$CKPT" \
    https://github.com/ChaoningZhang/MobileSAM/raw/master/weights/mobile_sam.pt
fi

echo ""
echo "Done. Start the app with the checkpoint path set, e.g.:"
echo "  SAM_CHECKPOINT=\"$(pwd)/$CKPT\" python3 -m uvicorn api.main:app --port 8000"
echo ""
echo "Then the ✨ Click-segment button in the component author turns on."
