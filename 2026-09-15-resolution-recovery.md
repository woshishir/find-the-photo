# Find the Photo v0.2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Preserve the source aspect ratio in every crop and conditionally deliver a conservative processed companion for sub-20% crops or approved gentle corrections.

**Architecture:** Keep `crop_photo.py` authoritative for exact raw pixels, geometry validation, and area measurement. Add an isolated `process_crop.py` stage that consumes the raw render manifest plus optional correction instructions, validates strict safety limits, and writes reproducible processed PNGs without any network calls.

**Tech Stack:** Python 3.10+, Pillow 10–12, NumPy 1.26+, OpenCV Headless 4.10+, `unittest`, JSON manifests.

**Spec:** `docs/superpowers/specs/2026-09-15-resolution-recovery-design.md`

## Global Constraints

- Inputs remain still JPG/JPEG, PNG, and WebP only.
- Every crop uses the oriented source aspect ratio; normalized crop width and height differ by no more than `0.001`.
- Resolution Recovery triggers only when integer crop area divided by oriented source area is strictly below `0.20`.
- The existing 512 px raw short-edge minimum remains mandatory.
- Rotation is limited to `[-5.0, 5.0]` degrees.
- Perspective corner displacement is limited to `0.08` per normalized axis.
- Combined inpaint polygon area is limited to `0.01` of the crop.
- Raw crops are never modified or overwritten by processing.
- No external API, generative fill, neural synthesis, or object-aware reconstruction.
- Processed output follows raw output in user-visible delivery.

---

### Task 1: Source-aspect geometry and recovery metadata

**Files:**
- Modify: `tests/test_crop_photo.py`
- Modify: `scripts/crop_photo.py`
- Modify: `references/manifest-schema.md`

**Interfaces:**
- Consumes: normalized `box` objects already accepted by `render_crops()`.
- Produces: `validate_source_aspect_box(box, tolerance=0.001) -> None` and per-crop fields `source_area_pixels: int`, `crop_area_pixels: int`, `area_fraction: float`, `resolution_recovery_required: bool`.

- [ ] **Step 1: Write failing aspect-ratio tests**

Add tests that use a `1200×800` source. A valid same-ratio crop uses equal normalized extents, such as `{left: 0.1, top: 0.2, right: 0.6, bottom: 0.7}`. An invalid crop uses unequal extents, such as `{left: 0.1, top: 0.2, right: 0.7, bottom: 0.7}`.

Change the existing test helper's default box from normalized `0.5×1.0` to `0.5×0.5`, then update legacy assertions that intentionally exercise exact pixel geometry. Any legacy test using a non-square normalized extent must either become source-aspect compliant or explicitly test the new rejection behavior.

```python
def test_accepts_source_aspect_crop_and_reports_area_fraction(self):
    report = module.render_crops(source, manifest, output, min_short_edge=100)
    crop = report["crops"][0]
    self.assertAlmostEqual(crop["area_fraction"], 0.25, places=3)
    self.assertFalse(crop["resolution_recovery_required"])

def test_rejects_crop_that_changes_source_aspect_ratio(self):
    with self.assertRaisesRegex(module.CropError, "source aspect ratio"):
        module.render_crops(source, manifest, output, min_short_edge=100)
    self.assertFalse(output.exists())
```

- [ ] **Step 2: Run the new tests and verify RED**

Run:

```bash
python -m unittest tests.test_crop_photo.CropPhotoTests.test_accepts_source_aspect_crop_and_reports_area_fraction tests.test_crop_photo.CropPhotoTests.test_rejects_crop_that_changes_source_aspect_ratio -v
```

Expected: failures because aspect validation and area metadata do not exist.

- [ ] **Step 3: Add minimal geometry validation and metadata**

In `scripts/crop_photo.py`, validate normalized extents before output creation:

```python
ASPECT_TOLERANCE = 0.001
RECOVERY_THRESHOLD = 0.20

def validate_source_aspect_box(box: dict[str, float], tolerance: float = ASPECT_TOLERANCE) -> None:
    normalized_width = float(box["right"]) - float(box["left"])
    normalized_height = float(box["bottom"]) - float(box["top"])
    if abs(normalized_width - normalized_height) > tolerance:
        raise CropError("Candidate crop must preserve the source aspect ratio.")
```

After `_pixel_box`, calculate:

```python
source_area = width * height
crop_area = crop_width * crop_height
area_fraction = crop_area / source_area
```

Write the four documented fields into every render-manifest crop entry and use strict `< RECOVERY_THRESHOLD` for the trigger.

- [ ] **Step 4: Add the exact 20% boundary test**

Use a `1000×1000` source and a normalized square with side `sqrt(0.20)`. Assert that an integer crop whose computed area is at or above 20% does not trigger; separately use side `0.44` and assert that it does trigger. Assert against the reported integer `area_fraction`, not the proposed normalized area.

- [ ] **Step 5: Run the crop suite and verify GREEN**

```bash
python -m unittest tests.test_crop_photo -v
```

Expected: all crop tests pass with no warnings.

- [ ] **Step 6: Update the manifest reference and commit**

Document the source-aspect invariant and new area fields in `references/manifest-schema.md`.

```bash
git add tests/test_crop_photo.py scripts/crop_photo.py references/manifest-schema.md
git commit -m "feat: lock crops to source aspect ratio"
```

---

### Task 2: Deterministic Resolution Recovery

**Files:**
- Create: `tests/test_process_crop.py`
- Create: `scripts/process_crop.py`
- Modify: `requirements.txt`

**Interfaces:**
- Consumes: `RUN/final/render-manifest.json` and the raw PNGs named in `crops[].output_file`.
- Produces: `process_crops(render_manifest: str | Path, output_dir: str | Path, corrections: str | Path | None = None, overwrite: bool = False) -> dict[str, Any]`, `<id>-processed.png`, and `processing-manifest.json`.

- [ ] **Step 1: Write failing recovery tests**

Create a minimal render directory with a real raw PNG and render manifest. Cover:

```python
def test_sub_20_percent_crop_is_processed_to_source_dimensions(self):
    report = module.process_crops(render_manifest, output)
    with Image.open(output / "crop-01-processed.png") as result:
        self.assertEqual(result.size, (1200, 800))
    self.assertEqual(report["items"][0]["trigger"], ["resolution_recovery"])

def test_crop_at_or_above_20_percent_without_correction_is_skipped(self):
    report = module.process_crops(render_manifest, output)
    self.assertEqual(report["items"], [])
    self.assertFalse((output / "crop-01-processed.png").exists())
```

Also assert that a missing raw file and a raw-size/manifest mismatch raise `ProcessError` before output.

- [ ] **Step 2: Run recovery tests and verify RED**

```bash
python -m unittest tests.test_process_crop -v
```

Expected: import/load failure because `scripts/process_crop.py` does not exist.

- [ ] **Step 3: Implement manifest loading and recovery selection**

Create `ProcessError`, validate schema version `1.0`, resolve raw files relative to the render manifest, compare actual dimensions with `output_size`, and select entries only when `resolution_recovery_required is True` or the entry has a correction.

Expose a CLI:

```bash
python scripts/process_crop.py --render-manifest RUN/final/render-manifest.json --output-dir RUN/processed [--corrections RUN/corrections.json] [--overwrite]
```

- [ ] **Step 4: Implement the conservative enhancement pipeline**

Use `Image.Resampling.LANCZOS`; preserve alpha separately. Convert color content to RGB, calculate channel means, clamp gray-world gains to `[0.94, 1.06]`, then apply `Contrast(1.03)`, `Color(1.02)`, `UnsharpMask(radius=1.2, percent=90, threshold=3)`, and `Sharpness(1.10)`.

For sub-20% entries, target `source.oriented_size`. Record every fixed parameter and applied white-balance gain. Set `synthetic_content: false`, `interpolated_pixels: true`, and `color_adjustments_applied: true`.

- [ ] **Step 5: Add alpha, overwrite, and deterministic-manifest tests**

Verify RGBA output preserves alpha shape after resize, a second call fails without `overwrite=True`, and JSON read from disk equals the returned report.

- [ ] **Step 6: Run the processing suite and verify GREEN**

```bash
python -m unittest tests.test_process_crop -v
```

Expected: all recovery tests pass.

- [ ] **Step 7: Add dependencies and commit**

Pin compatible ranges:

```text
Pillow>=10,<13
numpy>=1.26,<3
opencv-python-headless>=4.10,<5
```

```bash
git add tests/test_process_crop.py scripts/process_crop.py requirements.txt
git commit -m "feat: add local resolution recovery"
```

---

### Task 3: Gentle geometry and local inpainting

**Files:**
- Modify: `tests/test_process_crop.py`
- Modify: `scripts/process_crop.py`
- Create: `references/correction-schema.md`

**Interfaces:**
- Consumes: optional correction JSON with `schema_version: "1.0"` and `corrections[]` keyed by final crop `id`.
- Produces: validated correction execution plus recorded fields `rotation_degrees`, `perspective_corners`, `inpaint_polygons`, and `inpainted_area_fraction`.

The correction item shape is:

```json
{
  "id": "02-unexpected",
  "rotation_degrees": -1.5,
  "perspective_corners": [[0.01, 0.02], [0.99, 0.01], [0.98, 0.99], [0.02, 0.98]],
  "inpaint_polygons": [[[0.10, 0.10], [0.12, 0.10], [0.12, 0.12], [0.10, 0.12]]]
}
```

Corner order is top-left, top-right, bottom-right, bottom-left. Omitted operations are identity operations.

- [ ] **Step 1: Write failing validation tests**

Add real-input tests asserting rejection of `5.01°`, a perspective point displaced more than `0.08` from its canonical corner, duplicate correction IDs, unknown crop IDs, malformed polygons, and combined polygon area above `0.01`.

- [ ] **Step 2: Run validation tests and verify RED**

```bash
python -m unittest tests.test_process_crop.ProcessCropTests.test_rejects_rotation_beyond_limit tests.test_process_crop.ProcessCropTests.test_rejects_perspective_beyond_limit tests.test_process_crop.ProcessCropTests.test_rejects_inpaint_area_beyond_limit -v
```

Expected: failures because correction parsing and limit checks do not exist.

- [ ] **Step 3: Implement correction parsing and validation**

Add constants `MAX_ROTATION_DEGREES = 5.0`, `MAX_PERSPECTIVE_DISPLACEMENT = 0.08`, and `MAX_INPAINT_AREA_FRACTION = 0.01`. Calculate polygon area with the shoelace formula in normalized coordinates. Reject the entire processing job before writing files if any entry is invalid.

- [ ] **Step 4: Write failing behavior tests**

Use a synthetic grid image to verify a `2°` rotation changes geometry without changing final aspect ratio; a mild perspective transform preserves output dimensions; and a small solid-color distraction changes only pixels inside or immediately adjacent to its rasterized mask.

- [ ] **Step 5: Implement corrections in fixed order**

Use OpenCV in this order:

1. perspective transform from `perspective_corners` to the full raw rectangle;
2. affine rotation around image center;
3. crop the largest centered rectangle with the source aspect ratio that excludes transformation borders;
4. local `cv2.inpaint(..., radius=3, flags=cv2.INPAINT_TELEA)` using the validated combined mask;
5. resize to the target dimensions selected by Task 2;
6. run the enhancement pipeline.

For correction-only entries at or above 20% coverage, target the original raw crop dimensions. For entries below 20%, target the oriented source dimensions.

- [ ] **Step 6: Run all processing tests and verify GREEN**

```bash
python -m unittest tests.test_process_crop -v
```

Expected: all processing and correction tests pass.

- [ ] **Step 7: Document the correction schema and commit**

Document limits, semantic exclusions, normalized coordinates, identity defaults, and output ordering in `references/correction-schema.md`.

```bash
git add tests/test_process_crop.py scripts/process_crop.py references/correction-schema.md
git commit -m "feat: add bounded crop corrections"
```

---

### Task 4: Skill workflow and public documentation

**Files:**
- Modify: `SKILL.md`
- Modify: `README.md`
- Modify: `references/aesthetic-rubric.md`
- Modify: `references/manifest-schema.md`
- Modify: `tests/manual-evaluation.md`
- Modify: `agents/openai.yaml`

**Interfaces:**
- Consumes: the render and correction schemas from Tasks 1–3.
- Produces: a complete v0.2 agent workflow with raw-first paired delivery when processing triggers.

- [ ] **Step 1: Update `SKILL.md`**

Change the core principle to “crop first; process only when the area threshold or an approved correction requires it.” Require source-aspect proposals, blind review of raw crops only, post-selection correction instructions, processed-output inspection, and raw-first delivery. Link `references/correction-schema.md` only at the correction stage.

- [ ] **Step 2: Update aesthetic and manual evaluation guidance**

Teach the proposer that equal normalized box extents preserve source ratio. Add separate failure labels for aspect mismatch, overcorrection, geometry artifacts, inpaint artifacts, false detail, white-balance cast, and unnecessary processing.

- [ ] **Step 3: Update README and UI metadata**

Replace the absolute “No filters. No generation. Just a better rectangle.” claim with “Crop first. Recover only when needed.” Explain that raw results are always preserved, processing is conditional and local, and interpolated pixels are disclosed. Update the default prompt without changing implicit invocation policy.

- [ ] **Step 4: Validate documentation consistency**

```bash
rg -n "No filters|No upscaling|without resizing|generated_pixels.*false|recover_resolution|enhanced.png" SKILL.md README.md agents references tests
```

Expected: no stale unconditional claims or obsolete filenames.

- [ ] **Step 5: Commit documentation**

```bash
git add SKILL.md README.md agents/openai.yaml references tests/manual-evaluation.md
git commit -m "docs: publish find-the-photo v0.2 workflow"
```

---

### Task 5: Full verification, cloud photo test, and release package

**Files:**
- Modify only if verification exposes a defect: files owned by Tasks 1–4
- Create outside git tree: `find-the-photo-v0.2.0.zip`

**Interfaces:**
- Consumes: the complete v0.2 skill.
- Produces: verified git tag `v0.2.0` and a downloadable release archive.

- [ ] **Step 1: Run the complete automated suite**

```bash
python -m unittest discover -s tests -v
python scripts/prepare_photo.py --help
python scripts/crop_photo.py --help
python scripts/process_crop.py --help
```

Expected: zero failures and all three CLIs exit successfully.

- [ ] **Step 2: Run official skill validation**

```bash
python /root/.codex/skills/.system/skill-creator/scripts/quick_validate.py /workspace/scratch/516757b099bc/find-the-photo
```

Expected: validator reports the skill is valid.

- [ ] **Step 3: Run a cloud-only real-photo smoke test**

Use one user-uploaded test image already present in the cloud workspace. Create a same-aspect crop below 20%, render it, run `process_crop.py`, and verify:

- raw output remains an exact source crop;
- processed output has the oriented source dimensions;
- manifests disclose every operation;
- no network request occurs;
- visual inspection shows no strong halo, cast, warp, or invented object.

- [ ] **Step 4: Verify repository state and tag**

```bash
git diff --check
git status --short
git log --oneline --decorate -8
git tag v0.2.0
```

Expected: clean working tree before tagging and `v0.2.0` points at the verified release commit.

- [ ] **Step 5: Build and save the release archive**

Create `find-the-photo-v0.2.0.zip` from tracked files only, excluding `.git`, prior run artifacts, caches, and test outputs. Save the finished archive as a persistent user-facing file and provide direct links to the package and smoke-test comparison images.
