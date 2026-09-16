# Find the Photo v0.2 — Aspect-Locked Crops, Gentle Correction, and Resolution Recovery

## Goal

Keep every delivered crop at the source photograph's aspect ratio. When a selected crop contains less than 20% of the source image area, also deliver a conservative enhanced version that is restored to the source image's oriented pixel dimensions. Allow tightly bounded automatic correction for visibly tilted geometry, mild perspective distortion, and tiny simple distractions.

The raw crop remains the photographic record. Any processed version must remain recognizably the same photograph and must not reconstruct hidden subject detail.

## Product Rules

1. Every proposed, rendered, and delivered crop must preserve the source aspect ratio.
2. Aspect preservation is expressed in normalized coordinates: crop width and crop height must be equal within a small rounding tolerance. Pixel dimensions may differ by one pixel after floor/ceiling conversion.
3. Coverage is calculated from the final integer pixel crop area divided by the oriented source pixel area.
4. A coverage value strictly below `0.20` triggers Resolution Recovery. Exactly `0.20` does not.
5. The existing 512 px minimum short-edge rule remains in force before recovery. Enhancement is not permission to use an unusably small source fragment.
6. For a triggered crop, delivery order is:
   - the exact raw crop;
   - the enhanced crop.
7. The enhanced crop is resized to the full oriented source dimensions. It therefore has the source width, height, and aspect ratio.
8. Crops at or above 20% coverage deliver only the raw crop.
9. Rule 8 has one exception: if a crop needs an approved gentle correction, deliver the raw crop followed by a corrected version even when coverage is at or above 20%.
10. Approved correction limits are:
    - rotation no greater than 5 degrees in either direction;
    - normalized perspective displacement no greater than 8% on either axis;
    - inpainting masks with a combined area no greater than 1% of the crop.
11. Inpainting must not touch a face, body, license plate, readable text, defining subject edge, or other semantically important content. It may remove only tiny simple distractions such as dust, a thin wire, or a small edge fragment over a predictable background.
12. If a proposed correction exceeds any limit or requires guessing hidden content, skip the correction and return the raw crop.

## Processing Architecture

### Exact crop renderer

`scripts/crop_photo.py` remains authoritative for geometry and raw pixels. It will:

- reject crop boxes that do not match the source aspect ratio;
- continue applying EXIF orientation before cropping;
- continue rendering raw PNG files without resizing or filtering;
- add `source_area_pixels`, `crop_area_pixels`, `area_fraction`, and `resolution_recovery_required` to each crop's render-manifest entry.

### Processed-image pipeline

A new `scripts/process_crop.py` will read an existing `render-manifest.json`, its raw PNG files, and an optional correction manifest. It will process entries when either Resolution Recovery or an approved gentle correction is required.

Correction instructions are proposed automatically by the visual agent after final raw-crop inspection. A crop may specify:

- a signed rotation angle;
- a normalized four-corner perspective transform;
- one or more normalized polygon masks for local inpainting.

The script validates all numeric limits before writing output. The visual agent remains responsible for semantic exclusions such as faces, text, and subject contours, then must inspect the processed result for artifacts.

The deterministic local pipeline will:

1. apply approved perspective, rotation, and local inpainting operations;
2. crop away transformation borders while preserving the source aspect ratio;
3. resize back to the raw crop dimensions when correction alone triggered processing;
4. resize to the oriented source dimensions with Lanczos when coverage is below 20%;
5. apply bounded gray-world white-balance gains;
6. apply mild contrast and color balancing;
7. apply conservative unsharp masking and sharpness enhancement;
8. preserve transparency when technically possible and reject operations that cannot preserve it safely;
9. write `<crop-id>-processed.png` plus `processing-manifest.json`.

White-balance gains must be clamped so a dominant scene color is not neutralized. Enhancement parameters remain fixed and recorded for reproducibility.

Local inpainting may interpolate pixels only inside validated masks; it is not permission to remove or reconstruct meaningful content. The script must not use generative fill, external APIs, neural image synthesis, or object-aware hallucination. The processing manifest will explicitly distinguish geometry changes, inpainted pixels, interpolation, and color/detail processing.

## Workflow Changes

The proposer must create only source-aspect crop candidates. The blind critic still sees raw candidate crops, not enhanced versions, so aesthetic selection is based on composition rather than post-processing.

After final raw crops pass edge inspection:

1. identify only necessary corrections and write the optional correction manifest;
2. run the processed-image pipeline on the final render directory;
3. inspect every processed file for halos, color casts, clipped highlights, warped geometry, repeated textures, inpainting artifacts, and alpha errors;
4. present each triggered pair with raw first and processed second;
5. state whether area recovery, geometric correction, local inpainting, or a combination triggered processing.

The existing Safe, Editorial, and Unexpected roles and quality gate remain unchanged.

## Output and Metadata

Raw files keep their existing names, such as `02-unexpected.png`. Processed files use `02-unexpected-processed.png`.

The processing manifest records:

- input raw filename and dimensions;
- source target dimensions;
- crop coverage and trigger threshold;
- processed filename and dimensions;
- validated rotation, perspective, and inpainting instructions;
- transformed-border crop, when applied;
- resize method;
- white-balance gain bounds and applied gains;
- contrast, color, sharpness, and unsharp-mask parameters;
- `synthetic_content: false`;
- `interpolated_pixels: true`;
- `inpainted_area_fraction`;
- `color_adjustments_applied: true`.

## Errors and Safety

- Reject a crop with the wrong aspect ratio before writing any outputs.
- Refuse to overwrite raw or processed files unless `--overwrite` is explicitly passed.
- Reject inconsistent or incomplete render manifests.
- Reject processing when a listed raw crop is missing or its actual dimensions differ from the manifest.
- Reject rotation, perspective displacement, or combined inpaint area beyond its documented limit.
- Never silently skip a crop marked for processing.
- Preserve the existing supported input formats: JPG/JPEG, PNG, and still WebP.
- Use no network access. Runtime image operations may use Python, Pillow, NumPy, and OpenCV Headless only.

## Tests

Automated tests will verify:

- source-aspect crop boxes are accepted;
- mismatched crop boxes are rejected before output;
- pixel rounding stays within the documented tolerance;
- coverage below 20% triggers recovery;
- coverage at 20% does not trigger recovery;
- raw crop pixels remain unchanged;
- processed output for a sub-20% crop matches the oriented source dimensions;
- alpha is preserved;
- processed output differs from the raw crop after resizing/processing;
- correction-only output retains the raw crop dimensions and source aspect ratio;
- rotations beyond 5 degrees are rejected;
- perspective displacement beyond 8% is rejected;
- combined inpainting area beyond 1% is rejected;
- an accepted tiny inpaint mask changes pixels only in or immediately around the requested region;
- missing or inconsistent inputs fail clearly;
- overwrite protection remains intact;
- the complete existing test suite continues to pass.

## Documentation and Versioning

Update `SKILL.md`, `README.md`, `references/aesthetic-rubric.md`, `references/manifest-schema.md`, `agents/openai.yaml`, and manual evaluation guidance. Tag the completed release as `v0.2.0` after verification.
