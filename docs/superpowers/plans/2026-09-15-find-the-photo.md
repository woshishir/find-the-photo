# Find the Photo v0.1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a portable image-cropping agent skill that proposes, renders, blindly critiques, and returns up to three strong crops without editing pixels.

**Architecture:** The agent performs the visual judgment and writes normalized crop manifests. A deterministic Pillow script owns file validation, EXIF orientation, coordinate conversion, exact cropping, PNG output, and reproducibility metadata.

**Tech Stack:** Python 3.10+, Pillow, `unittest`, Agent Skills markdown/YAML.

**Spec:** `docs/superpowers/specs/2026-09-15-find-the-photo-design.md`

## Global Constraints

- Input formats are JPG, JPEG, PNG, and WebP only.
- Output crops are PNG and contain no generated, filtered, or retouched pixels.
- The blind critic receives candidates only, never the source image or proposer explanations.
- Final delivery contains zero to three crops and never pads weak results.

---

### Task 1: Deterministic crop engine

**Files:**
- Create: `tests/test_crop_photo.py`
- Create: `scripts/crop_photo.py`
- Create: `requirements.txt`

**Interfaces:**
- Consumes: source image path, versioned JSON manifest, output path, minimum short edge, overwrite flag.
- Produces: PNG crops plus `render-manifest.json`; importable `load_oriented_image()` and `render_crops()` functions.

- [ ] Write tests for supported formats, EXIF orientation, exact decoded pixels, schema validation, minimum resolution, spoofed formats, and overwrite protection.
- [ ] Run `python -m unittest discover -s tests -v` and verify failure because `scripts/crop_photo.py` does not exist.
- [ ] Implement the smallest crop engine satisfying the tests.
- [ ] Re-run the suite and verify all tests pass.
- [ ] Commit the working crop engine.

### Task 2: Skill behavior and contracts

**Files:**
- Create: `SKILL.md`
- Create: `references/aesthetic-rubric.md`
- Create: `references/manifest-schema.md`
- Create: `agents/openai.yaml`

**Interfaces:**
- Consumes: a user-provided supported image and optional aspect-ratio/output preferences.
- Produces: candidate manifest, blind scorecard, final manifest, and up to three rendered crops.

- [ ] Define the proposer recipe, critic isolation contract, selection threshold, and final response contract.
- [ ] Document the exact manifest schema used by the crop engine.
- [ ] Add UI metadata with automatic invocation enabled.
- [ ] Run the official `quick_validate.py` validator and fix every reported issue.
- [ ] Commit the validated skill instructions.

### Task 3: GitHub package and end-to-end verification

**Files:**
- Create: `README.md`
- Create: `LICENSE`
- Create: `.gitignore`

**Interfaces:**
- Consumes: a clean checkout and one supported photograph.
- Produces: a tested GitHub-ready repository and ZIP archive.

- [ ] Document installation, the user experience, limits, privacy, and example invocation.
- [ ] Run unit tests, CLI help, validator, placeholder scan, and a synthetic image smoke test.
- [ ] Confirm Git status contains only intended source files, then commit.
- [ ] Create `find-the-photo-v0.1.0.zip` without caches or generated outputs.
