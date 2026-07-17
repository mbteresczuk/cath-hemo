# Mullins style dataset

140 paired examples.

- `images/<id>.png` + `images/<id>.txt` — target + caption (LoRA style fine-tune)
- `control/<id>.png` — structure map (ControlNet phase)
- `metadata.jsonl` — diffusers format
- trigger token: `mullinsdiagram`

## Go/no-go test
Train a LoRA on images/ + captions, then prompt with `mullinsdiagram, ...` to see if the Mullins style is learnable.
