#!/usr/bin/env python3
"""
Phase 1 harmonization test — does EDGE-conditioning preserve an added feature
(where plain img2img dropped it) while rendering it in native Mullins style?

Approach (place -> harmonize, harmonize half):
    composed draft (correct anatomy, rough seams)
      -> canny edge map (locks every drawn line, INCLUDING the added feature)
      -> FLUX + a pretrained CANNY ControlNet + the Mullins style LoRA
      -> redraws those exact lines in professional Mullins ink

The canny ControlNet forces the output to follow the draft's lines, so the added
PDA/ASD cannot be smoothed away (the failure mode of plain img2img); the LoRA
supplies the hand-drawn look. Sweep the controlnet scale to find where the
feature is preserved AND the style is clean.

Reads the draft from the volume at hybrid_init/<dtag>.png (uploaded from the
illustrator). Writes results/HARM_<dtag>_sweep.png = draft | canny | gen@scales.

Run:
  cd training
  python3 -m modal run modal_harmonize.py --dtag ASD_PDA --scales "0.5,0.7,0.9" --res 1024
  python3 -m modal volume get mullins-controlnet-output results/HARM_ASD_PDA_sweep.png ./results/HARM_ASD_PDA_sweep.png
"""
import os

import modal

HERE = os.path.dirname(os.path.abspath(__file__))
LOCAL_DATASET = os.path.join(HERE, "dataset_controlnet")
DIFFUSERS_TAG = "v0.31.0"
BASE_MODEL = "black-forest-labs/FLUX.1-dev"
# Pretrained FLUX canny ControlNet (open weights); locks the draft's line-art.
CANNY_CN = "InstantX/FLUX.1-dev-Controlnet-Canny"
BASE_PROMPT = ("mullinsdiagram, a hand-drawn Mullins-style line diagram of a "
               "congenital heart, clean black ink on white background")

app = modal.App("mullins-harmonize")
hf_cache = modal.Volume.from_name("hf-cache", create_if_missing=True)
out_vol = modal.Volume.from_name("mullins-controlnet-output", create_if_missing=True)

image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("git")
    .pip_install("torch", "torchvision")
    .run_commands(
        f"git clone --depth 1 --branch {DIFFUSERS_TAG} "
        "https://github.com/huggingface/diffusers /root/diffusers",
        "pip install -e /root/diffusers",
        "pip install -r /root/diffusers/examples/controlnet/requirements_flux.txt",
        "pip install 'transformers==4.44.2' sentencepiece protobuf peft opencv-python-headless",
        "pip install 'fastapi[standard]'",   # required for the @modal.fastapi_endpoint web route
    )
    .add_local_dir(LOCAL_DATASET, remote_path="/root/dataset_controlnet")
)


@app.function(
    image=image, gpu="A100-80GB", timeout=60 * 60,
    volumes={"/root/.cache/huggingface": hf_cache, "/root/output": out_vol},
    secrets=[modal.Secret.from_name("huggingface")],
)
def harmonize(dtag: str = "ASD_PDA",
              lora: str = "/root/output/lora/lora.safetensors",
              scales: str = "0.5,0.7,0.9", res: int = 1024,
              steps: int = 28, guidance: float = 3.5,
              canny_low: int = 80, canny_high: int = 200, seed: int = 0):
    import cv2
    import numpy as np
    import torch
    from diffusers import FluxControlNetModel, FluxControlNetPipeline
    from PIL import Image

    os.environ["HUGGING_FACE_HUB_TOKEN"] = os.environ.get("HF_TOKEN", "")
    os.environ["HF_HOME"] = "/root/.cache/huggingface"

    controlnet = FluxControlNetModel.from_pretrained(CANNY_CN, torch_dtype=torch.bfloat16)
    pipe = FluxControlNetPipeline.from_pretrained(
        BASE_MODEL, controlnet=controlnet, torch_dtype=torch.bfloat16)
    pipe.to("cuda")
    if lora and os.path.exists(lora):
        pipe.load_lora_weights(os.path.dirname(lora), weight_name=os.path.basename(lora))
        print("loaded LoRA:", lora, flush=True)

    draft = Image.open(f"/root/output/hybrid_init/{dtag}.png").convert("RGB").resize((res, res))
    # canny edges of the draft -> the control (white lines on black, 3-ch)
    gray = cv2.cvtColor(np.array(draft), cv2.COLOR_RGB2GRAY)
    edges = cv2.Canny(gray, canny_low, canny_high)
    canny_img = Image.fromarray(np.stack([edges] * 3, axis=-1))

    sc = [float(s) for s in scales.split(",") if s.strip()]
    results_dir = "/root/output/results"
    os.makedirs(results_dir, exist_ok=True)

    gens = []
    for s in sc:
        print(f"harmonize {dtag} canny-scale={s}, {res}px …", flush=True)
        out = pipe(
            prompt=BASE_PROMPT,
            control_image=canny_img,
            controlnet_conditioning_scale=s,
            num_inference_steps=steps,
            guidance_scale=guidance,
            height=res, width=res,
            generator=torch.Generator("cuda").manual_seed(seed),
        ).images[0]
        gens.append((s, out))
        out.save(os.path.join(results_dir, f"HARM_{dtag}_c{s}.png"))

    # strip: draft | canny | gen@scales
    strip = Image.new("RGB", (res * (2 + len(gens)), res), "white")
    strip.paste(draft, (0, 0))
    strip.paste(canny_img.resize((res, res)), (res, 0))
    for i, (s, g) in enumerate(gens, start=2):
        strip.paste(g, (res * i, 0))
    strip.save(os.path.join(results_dir, f"HARM_{dtag}_sweep.png"))
    out_vol.commit()
    print(f"Done. results/HARM_{dtag}_sweep.png  (draft | canny | " +
          " | ".join(f"c{s}" for s, _ in gens) + ")", flush=True)


@app.local_entrypoint()
def main(dtag: str = "ASD_PDA",
         lora: str = "/root/output/lora/lora.safetensors",
         scales: str = "0.5,0.7,0.9", res: int = 1024,
         steps: int = 28, guidance: float = 3.5,
         canny_low: int = 80, canny_high: int = 200, seed: int = 0):
    harmonize.remote(dtag=dtag, lora=lora, scales=scales, res=res, steps=steps,
                     guidance=guidance, canny_low=canny_low, canny_high=canny_high, seed=seed)


# ── Served endpoint for the app (place happens app-side; this harmonizes) ──────
# Deploy once:   modal deploy training/modal_harmonize.py
# It prints a URL for `Harmonizer.web`; set it as MULLINS_HARMONIZE_URL for the
# FastAPI app, which POSTs {"draft_b64","scale","res"} and gets {"image_b64"}.
LORA_PATH = "/root/output/lora/lora.safetensors"


@app.cls(
    image=image, gpu="A100-80GB",
    volumes={"/root/.cache/huggingface": hf_cache, "/root/output": out_vol},
    secrets=[modal.Secret.from_name("huggingface")],
    scaledown_window=300,   # keep the loaded model warm 5 min between requests
)
class Harmonizer:
    @modal.enter()
    def load(self):
        import torch
        from diffusers import FluxControlNetModel, FluxControlNetPipeline

        os.environ["HUGGING_FACE_HUB_TOKEN"] = os.environ.get("HF_TOKEN", "")
        os.environ["HF_HOME"] = "/root/.cache/huggingface"
        controlnet = FluxControlNetModel.from_pretrained(CANNY_CN, torch_dtype=torch.bfloat16)
        self.pipe = FluxControlNetPipeline.from_pretrained(
            BASE_MODEL, controlnet=controlnet, torch_dtype=torch.bfloat16)
        self.pipe.to("cuda")
        if os.path.exists(LORA_PATH):
            self.pipe.load_lora_weights(os.path.dirname(LORA_PATH),
                                        weight_name=os.path.basename(LORA_PATH))

    def _run(self, draft, scale, res, steps, guidance, canny_low, canny_high, seed):
        import cv2
        import numpy as np
        import torch
        from PIL import Image

        draft = draft.convert("RGB").resize((res, res))
        gray = cv2.cvtColor(np.array(draft), cv2.COLOR_RGB2GRAY)
        edges = cv2.Canny(gray, canny_low, canny_high)
        canny_img = Image.fromarray(np.stack([edges] * 3, axis=-1))
        return self.pipe(
            prompt=BASE_PROMPT, control_image=canny_img,
            controlnet_conditioning_scale=scale, num_inference_steps=steps,
            guidance_scale=guidance, height=res, width=res,
            generator=torch.Generator("cuda").manual_seed(seed),
        ).images[0]

    @modal.fastapi_endpoint(method="POST")
    def web(self, data: dict):
        """POST {"draft_b64": <png b64>, "scale": 0.9, "res": 1024} -> {"image_b64"}."""
        import base64
        import io
        from PIL import Image

        draft = Image.open(io.BytesIO(base64.b64decode(data["draft_b64"])))
        out = self._run(
            draft,
            scale=float(data.get("scale", 0.9)),
            res=int(data.get("res", 1024)),
            steps=int(data.get("steps", 28)),
            guidance=float(data.get("guidance", 3.5)),
            canny_low=int(data.get("canny_low", 80)),
            canny_high=int(data.get("canny_high", 200)),
            seed=int(data.get("seed", 0)),
        )
        buf = io.BytesIO()
        out.save(buf, format="PNG")
        return {"image_b64": base64.b64encode(buf.getvalue()).decode()}
