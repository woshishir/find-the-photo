# Manifest Schema

The crop engine consumes UTF-8 JSON with normalized coordinates measured on the EXIF-oriented image. The top-left corner is `(0, 0)` and the bottom-right is `(1, 1)`.

## Candidate or final manifest

```json
{
  "schema_version": "1.0",
  "candidates": [
    {
      "id": "crop-01",
      "role": "unexpected",
      "box": {
        "left": 0.08,
        "top": 0.12,
        "right": 0.74,
        "bottom": 0.78
      },
      "proposal_reason": "The empty wall becomes active negative space."
    }
  ]
}
```

Rules:

- `schema_version` must be `"1.0"`.
- `candidates` contains 1–12 items for rendering.
- `id` is a unique lowercase slug containing letters, numbers, hyphens, or underscores; use neutral candidate IDs during blind review.
- `role` is exactly `safe`, `editorial`, or `unexpected` for candidate compatibility. v0.3 proposal and final manifests use only `unexpected`; the final manifest contains exactly one item.
- `left`, `top`, `right`, and `bottom` are finite numbers from 0 through 1, with positive width and height.
- Normalized width (`right - left`) and height (`bottom - top`) must differ by no more than `0.001`. Equal normalized extents preserve the EXIF-oriented source aspect ratio.
- `proposal_reason` is one concise, non-empty sentence.
- Every rendered crop must occupy strictly less than 50% of the oriented source pixel area. The renderer rejects an area fraction of `0.50` or higher.
- The script converts normalized coordinates to an outer integer-pixel box, clips to the oriented image bounds, then trims inward symmetrically. It uses the exact reduced source ratio when that does not require materially more trimming; otherwise it chooses the nearest integer dimensions with no more than half a pixel of equivalent aspect error. It never stretches or resizes a raw crop.

## Render manifest

`scripts/crop_photo.py` writes `render-manifest.json` beside the PNGs. It records:

- source filename, format, SHA-256, original size, oriented size, and whether EXIF orientation was applied;
- normalized and pixel crop boxes;
- output filename, pixel dimensions, reduced aspect ratio, and role;
- source and crop pixel areas, exact integer-pixel `area_fraction`, and whether the strict sub-20% Resolution Recovery trigger applies;
- explicit flags confirming PNG output, no resizing, no filters, and no generated pixels.
- whether the render is a final selection; final renders are created with `--final-selection` and contain exactly one `unexpected` crop.

The render manifest is authoritative for technical checks. The separate blind-critic scorecard remains authoritative for aesthetic selection.

## Processing manifest

`scripts/process_crop.py` reads the final render manifest and writes `processing-manifest.json`. It records why each processed companion was created, its target dimensions, white-balance gains, enhancement parameters, geometry instructions, inpaint area, and explicit disclosure of interpolated pixels and color adjustments. Crops at or above 20% with no correction produce no processed companion.

Correction instructions use [the gentle correction schema](correction-schema.md).

## Re-rendering finalists

Create `final.json` by copying only the single Discovery-Gate winner, keeping its exact normalized box and role `unexpected`. Render from the original source, not from candidate PNGs, with `--final-selection`, so the final is one source crop operation and cannot silently expand into multiple outputs.
