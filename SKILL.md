---
name: find-the-photo
description: Use when a user wants one genuinely unexpected photograph discovered inside a JPG, JPEG, PNG, or WebP image, especially when a small crop may need conservative resolution recovery.
---

# Find the Photo

Find one photograph hidden inside the uploaded image. The deliverable is a single, genuinely unexpected `unexpected` crop—not a safer version of the original. Crop first; process only when a small crop or a necessary, tightly bounded correction requires it. Always preserve the untouched raw crop.

## Requirements

- A visual-capable agent and Python 3.10+ with Pillow, NumPy, and OpenCV Headless.
- One still JPG, JPEG, PNG, or WebP image.
- Use the bundled scripts; do not recreate their image operations ad hoc.

## Workflow

1. Create a new run directory. Never overwrite an earlier run unless the user explicitly asks.
2. Run:

   ```bash
   python scripts/prepare_photo.py INPUT --output-dir RUN/input
   ```

3. Inspect only `RUN/input/source-oriented.png`. If decoding fails or the source is unsupported, return the script error and stop.
4. Read [the aesthetic rubric](references/aesthetic-rubric.md). Propose 6–10 candidates using its proposer recipe and write `RUN/candidates.json` using [the manifest schema](references/manifest-schema.md). Every box must preserve the source aspect ratio: normalized width and height are equal within `0.001`. Every candidate must be intended as an `unexpected` discovery and must occupy less than 50% of the source area after integer rendering. Use neutral IDs such as `crop-01`; do not reveal roles in filenames.
5. Render candidates:

   ```bash
   python scripts/crop_photo.py --source INPUT --manifest RUN/candidates.json --output-dir RUN/candidates
   ```

6. Run a blind critic pass using the rendered candidate PNGs and the rubric. The critic receives neither the source, candidate manifest, proposer reasoning, nor role labels. When a fresh visual subagent is available and authorized, give it only those PNGs and the critic rubric. Otherwise begin a separate inspection pass and reopen only candidate PNGs.
7. Run the Discovery Gate with the source preview and the blind keepers. This is a separate comparison pass: reject any crop that still reads like the original composition, merely removes a little border, or depends on the original context. Prefer a detail, gesture, texture, reflection, spatial relationship, or strong geometric fragment that can stand alone. If no candidate passes both gates, return no crop.
8. Select exactly one winner. Write only that box to `RUN/final.json` with role `unexpected`, then render it from the source into `RUN/final` with `--final-selection`. The renderer enforces one final crop and the strict `<50%` area limit. Inspect the raw final for accidental edge cuts or technical errors.
9. If the final needs straightening, mild perspective correction, or a tiny simple distraction removed, read [the correction schema](references/correction-schema.md) and write `RUN/corrections.json`. Do not create corrections for an already clean crop.
10. Run conditional processing:

    ```bash
    python scripts/process_crop.py --render-manifest RUN/final/render-manifest.json --output-dir RUN/processed
    ```

    When step 9 produced a correction manifest, append `--corrections RUN/corrections.json`.

    A crop below 20% of source area is restored to the oriented source dimensions. A valid correction also triggers processing. Inspect every processed PNG and discard it if it shows halos, casts, warping, repeated texture, or repair artifacts.
11. Return either zero or one photograph with one short reason. When processing triggered, show the raw crop first and processed companion second. State the trigger and operations. Keep coordinates and scores in the run files unless requested.

## Non-negotiable boundaries

- Judge each crop as if it were the only photograph the viewer saw, then separately compare it with the source to confirm that it is genuinely transformed.
- The final deliverable is exactly one crop with role `unexpected`, or no crop when the quality bar is not met.
- The rendered final crop must occupy strictly less than 50% of the oriented source pixel area. A crop at or above 50% is not an output, even if it looks attractive.
- Do not output `safe` or `editorial` alternatives. They are not final roles in v0.3.
- Do not center the subject by default; choose the frame that creates the strongest hierarchy, tension, rhythm, or negative space.
- Reject timid crops that preserve the original subject, horizon, spatial layout, or visual story with only modest trimming. A smaller copy of the original is not an `unexpected` discovery.
- Favor local stories and abstractions: a pair of figures in relation, a reflection or water texture, a diagonal railing or shoreline, a patch of light, or a fragment whose meaning changes when isolated.
- Reject awkward cuts through faces, hands, feet, joints, text, or dominant geometry unless the cut is clearly intentional.
- Reject crops below the script's default 512 px short-edge threshold.
- Preserve the source aspect ratio; never stretch.
- Keep correction within ±5° rotation, 8% normalized perspective displacement, and 1% combined inpaint area.
- Never inpaint a face, body, license plate, readable text, defining subject edge, or content whose hidden appearance must be guessed.
- Do not use generative fill, neural synthesis, external image APIs, object removal, or factual detail reconstruction. Resolution Recovery may interpolate pixels and apply bounded white balance, contrast, color, and sharpness only in the processed companion.
- If no candidate is genuinely worth keeping, return no crop and explain that crop alone cannot rescue this source.

## Final response shape

Lead with `Found 1 unexpected photo inside this image.` or `I couldn't find a strong unexpected photo in this image.` Label the result `Unexpected`. For a processed pair, show `Raw` then `Processed` and disclose area recovery, geometry correction, or local inpainting. End by stating that the raw crop was preserved and no generative fill or external image API was used.
