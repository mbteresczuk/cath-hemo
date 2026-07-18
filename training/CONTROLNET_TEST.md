# ControlNet test: does structure control hold at v2 quality?

The style LoRA works (proven). Now the question: if we feed the parametric
structure map as a control image, does the model draw THAT anatomy — in the
Mullins style — instead of an invented heart?

## What we're feeding
Parametric control maps are in `training/control_test/`:
- `normal_Dloop.png`
- `DORV_Dloop_PS.png`
- `DORV_Lloop_PS.png`   ← the target case
- `dTGA_Dloop.png`

Regenerate/any anatomy:
`python3 training/render_control.py --loop L --va dorv --ps --out ctrl.png`

## The approach (cheapest first)

**Phase A — pretrained ControlNet + your LoRA (fast, ~$1–3, no new training).**
Run FLUX inference with THREE inputs at once:
  1. your trained Mullins LoRA (from the go/no-go test)
  2. a FLUX ControlNet (canny or HED type)
  3. a control map from `control_test/` as the control image
Prompt: `mullinsdiagram, a hand-drawn Mullins-style line diagram of a
congenital heart, double outlet right ventricle, L-loop, pulmonary stenosis,
black ink on white background`
ControlNet strength: start ~0.6–0.8.

Read the result:
- Output follows the control's layout (silhouette, arch, vessels where the
  map puts them) AND looks Mullins → **structure control holds.** Done — I
  wire it into the app.
- Output is Mullins-styled but ignores the layout → pretrained ControlNet is
  too loose for clean line-art. Go to Phase B.
- Output follows layout but looks bad / not Mullins → LoRA+ControlNet need
  balancing (adjust strengths); iterate.

**Phase B — train a custom ControlNet (only if A is too loose, ~$15–40).**
Train a ControlNet on our paired data: `training/dataset/control/<id>.png`
(structure) → `training/dataset/images/<id>.png` (target). This teaches it
exactly our structure→Mullins mapping. More involved (diffusers ControlNet
training on a GPU), but tightest control.

## Easiest way to actually run Phase A

Combining a custom LoRA + a ControlNet in one call is fiddly to click through.
Two options:

- **Let me run it.** Create a Replicate API token (Account → API tokens) and
  share it; I'll script Phase A from here — pick the model, wire your LoRA +
  the control maps, run all four cases, and show you the results. Costs a few
  dollars on your account. Simplest for you.
- **DIY.** On Replicate, find a FLUX model that accepts a LoRA + a ControlNet
  image (e.g. a `flux-dev-controlnet` community model with an `hf_lora`
  input), upload a `control_test/` image, set the prompt above, run.

## The verdict this gives
This is the last real unknown. If Phase A or B follows the structure, the
whole "type any heart → Mullins diagram" feature works and I integrate it.
If neither can hold structure from these maps, we improve the parametric
renderer and retry — but the empirical result tells us which.
