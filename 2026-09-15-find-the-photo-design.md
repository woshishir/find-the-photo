# Find the Photo v0.1 Design

## Goal

Create a portable agent skill that discovers strong photographs hidden inside an ordinary or cluttered image by changing only the crop boundary.

## Product boundary

- Accept JPG, JPEG, PNG, and WebP still images.
- Apply EXIF orientation before any crop coordinates are interpreted.
- Do not generate, erase, retouch, filter, recolor, resize, sharpen, or relight pixels.
- Render every crop as PNG so the decoded source pixels are not changed by lossy re-encoding.
- Let a visual proposer create 6–10 materially different candidates across `safe`, `editorial`, and `unexpected` roles.
- Let a blind critic judge only the rendered candidates, without the source image or proposer explanations.
- Deliver at most three crops. Deliver one or two when fewer than three pass the quality bar.

## Workflow

1. Validate and visually inspect the source.
2. Propose normalized crop boxes in a versioned JSON manifest.
3. Render exact crops locally with Pillow.
4. Review candidates as independent photographs using a fixed rubric.
5. Select distinct winners and render them from the source into a final directory.
6. Return the images, concise reasons, and a machine-readable render manifest.

## Components

- `SKILL.md`: agent workflow and hard boundaries.
- `references/aesthetic-rubric.md`: proposer and blind-critic judgment criteria.
- `references/manifest-schema.md`: JSON input and output contracts.
- `scripts/crop_photo.py`: deterministic validation, EXIF transpose, crop rendering, and report generation.
- `tests/test_crop_photo.py`: observable format, orientation, pixel, validation, and CLI behavior.
- `README.md`: GitHub-facing explanation, install, and usage.

## Failure behavior

Unsupported or mislabeled files, invalid coordinates, unsafe IDs, undersized crops, duplicate IDs, and accidental overwrites fail with actionable errors. A weak photograph is not a technical failure: the skill returns fewer winners and explains that the quality threshold was not met.

## Acceptance criteria

- All automated tests and the official skill validator pass.
- A synthetic smoke test produces correctly sized PNG crops and a reproducible manifest.
- The repository contains no generated test outputs, cache directories, or placeholder text.
- The repository is committed to Git and packaged as a ZIP for testing.
