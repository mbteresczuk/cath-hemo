# Go/no-go test: is the Mullins style learnable?

Goal: spend ~$5–10 and ~30 min to see if an AI model can learn to draw in
your diagrams' hand-drawn style. If yes, the full "type any heart" feature is
green-lit. If no, you've spent $10 instead of weeks.

You do NOT need a GPU or any local ML setup — this all runs in a browser on
Replicate (the easiest on-ramp).

---

## Step 0 — build the upload file (already done for you)
The file to upload is:

    training/dataset/mullins_lora_dataset.zip

(If it's missing, regenerate: `python3 training/prepare_dataset.py`, then
`cd training/dataset/images && zip -r ../mullins_lora_dataset.zip . -i '*.png' '*.txt'`)

It contains 140 diagram images, each with a matching `.txt` caption.

---

## Step 1 — make a Replicate account
1. Go to https://replicate.com and sign up.
2. Add a payment method (Settings → Billing). Training/running costs a few
   dollars total; you're not committing to anything ongoing.

## Step 2 — start a LoRA training
1. Open the FLUX LoRA trainer:
   https://replicate.com/ostris/flux-dev-lora-trainer/train
2. Fill in:
   - **input_images**: upload `mullins_lora_dataset.zip`
   - **trigger_word**: `mullinsdiagram`
   - **steps**: `1200`  (good starting point for ~140 images)
   - leave the rest at defaults
3. Click **Create training**. It runs ~20–30 min. You can close the tab; it
   emails/keeps the result.

## Step 3 — generate test images
When training finishes, Replicate gives you a trained model. Open it and use
the **Run** tab. Try these prompts (the trigger word matters):

    mullinsdiagram, a hand-drawn Mullins-style line diagram of a congenital
    heart with tetralogy of Fallot, black ink on white background

    mullinsdiagram, a hand-drawn Mullins-style line diagram of a congenital
    heart, double outlet right ventricle with pulmonary stenosis

Generate 4–6 images per prompt.

## Step 4 — judge (this is the whole point)
Look at the samples and ask ONE question:

    Do these look like they belong in your Mullins diagram set —
    the line quality, the hand-drawn feel?

- **Yes / close** → the style is learnable. Tell me, and I build the next
  piece: feeding the parametric schematic in as a ControlNet so the anatomy
  is exactly what you typed (right now the model draws *a* heart, not *your*
  specified anatomy — that's the ControlNet's job, step 2 of the real build).
- **No / messy** → the style didn't transfer from 140 images. We stop here,
  ~$10 spent, and your 140-diagram retrieval stays the ceiling.

Don't judge anatomy yet — at this stage the model invents the anatomy. We're
only testing whether it can nail the *look*. Structure control comes after.

---

## Alternative: let me run it for you
If you'd rather not click through Replicate, create a Replicate API token
(Account → API tokens) and I can script the training + sampling from here.
That means sharing a token that can spend money, so only do it if you're
comfortable — the browser path above avoids that entirely.
