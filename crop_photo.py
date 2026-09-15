#!/usr/bin/env python3
"""Render exact, non-resized crops from normalized coordinates."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from pathlib import Path
from typing import Any

from PIL import Image, ImageOps, UnidentifiedImageError


SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
EXPECTED_FORMATS = {
    ".jpg": "JPEG",
    ".jpeg": "JPEG",
    ".png": "PNG",
    ".webp": "WEBP",
}
ALLOWED_ROLES = {"safe", "editorial", "unexpected"}
SAFE_ID = re.compile(r"^[a-z0-9](?:[a-z0-9_-]{0,62}[a-z0-9])?$")
SCHEMA_VERSION = "1.0"
ASPECT_TOLERANCE = 0.001
RECOVERY_THRESHOLD = 0.20
MAX_CROP_AREA_FRACTION = 0.50


class CropError(ValueError):
    """Raised when a source image or crop manifest is unsafe or invalid."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_oriented_image(source: str | Path) -> tuple[Image.Image, dict[str, Any]]:
    """Open a supported still image and apply its EXIF orientation."""
    path = Path(source)
    extension = path.suffix.lower()
    if extension not in SUPPORTED_EXTENSIONS:
        allowed = ", ".join(sorted(SUPPORTED_EXTENSIONS))
        raise CropError(f"Unsupported image extension '{extension}'. Expected one of: {allowed}.")
    if not path.is_file():
        raise CropError(f"Source image does not exist: {path}")

    try:
        with Image.open(path) as opened:
            source_format = (opened.format or "").upper()
            expected_format = EXPECTED_FORMATS[extension]
            if source_format != expected_format:
                raise CropError(
                    f"Image format {source_format or 'UNKNOWN'} does not match its extension "
                    f"{extension} (expected {expected_format})."
                )
            if getattr(opened, "is_animated", False):
                raise CropError("Animated images are not supported; provide a still image.")

            original_size = list(opened.size)
            orientation = opened.getexif().get(274, 1)
            icc_profile = opened.info.get("icc_profile")
            oriented = ImageOps.exif_transpose(opened).copy()
    except CropError:
        raise
    except (UnidentifiedImageError, OSError) as exc:
        raise CropError(f"Could not decode image: {path.name}") from exc

    metadata = {
        "filename": path.name,
        "format": source_format,
        "original_size": original_size,
        "oriented_size": list(oriented.size),
        "exif_orientation_applied": orientation not in (None, 1),
        "sha256": _sha256(path),
        "icc_profile": icc_profile,
    }
    return oriented, metadata


def _read_manifest(path: Path) -> list[dict[str, Any]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise CropError(f"Manifest does not exist: {path}") from exc
    except json.JSONDecodeError as exc:
        raise CropError(f"Manifest is not valid JSON: {exc.msg}") from exc

    if not isinstance(payload, dict) or payload.get("schema_version") != SCHEMA_VERSION:
        raise CropError(f"Manifest schema_version must be '{SCHEMA_VERSION}'.")
    candidates = payload.get("candidates")
    if not isinstance(candidates, list) or not 1 <= len(candidates) <= 12:
        raise CropError("Manifest candidates must contain between 1 and 12 crops.")

    seen: set[str] = set()
    for index, item in enumerate(candidates):
        if not isinstance(item, dict):
            raise CropError(f"Candidate {index} must be an object.")
        crop_id = item.get("id")
        if not isinstance(crop_id, str) or not SAFE_ID.fullmatch(crop_id):
            raise CropError(f"Candidate {index} id must be a safe lowercase slug.")
        if crop_id in seen:
            raise CropError(f"Duplicate candidate id: {crop_id}")
        seen.add(crop_id)
        if item.get("role") not in ALLOWED_ROLES:
            raise CropError(f"Candidate {crop_id} role must be safe, editorial, or unexpected.")
        reason = item.get("proposal_reason")
        if not isinstance(reason, str) or not reason.strip():
            raise CropError(f"Candidate {crop_id} requires a non-empty proposal_reason.")

        box = item.get("box")
        if not isinstance(box, dict):
            raise CropError(f"Candidate {crop_id} requires a box object.")
        coordinates = []
        for key in ("left", "top", "right", "bottom"):
            value = box.get(key)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise CropError(f"Candidate {crop_id} box.{key} must be a number.")
            value = float(value)
            if not math.isfinite(value) or not 0 <= value <= 1:
                raise CropError(f"Candidate {crop_id} coordinates must be between 0 and 1.")
            coordinates.append(value)
        left, top, right, bottom = coordinates
        if left >= right or top >= bottom:
            raise CropError(f"Candidate {crop_id} box must have positive width and height.")
    return candidates


def _pixel_box(box: dict[str, float], width: int, height: int) -> tuple[int, int, int, int]:
    left = math.floor(float(box["left"]) * width)
    top = math.floor(float(box["top"]) * height)
    right = math.ceil(float(box["right"]) * width)
    bottom = math.ceil(float(box["bottom"]) * height)
    left, top = max(0, left), max(0, top)
    right, bottom = min(width, right), min(height, bottom)
    divisor = math.gcd(width, height)
    aspect_width = width // divisor
    aspect_height = height // divisor
    max_width = right - left
    max_height = bottom - top
    scale = min(max_width // aspect_width, max_height // aspect_height)
    exact_size = (aspect_width * scale, aspect_height * scale) if scale >= 1 else None
    nearest_sizes = []
    width_from_height = round(max_height * width / height)
    if 0 < width_from_height <= max_width:
        nearest_sizes.append((width_from_height, max_height))
    height_from_width = round(max_width * height / width)
    if 0 < height_from_width <= max_height:
        nearest_sizes.append((max_width, height_from_width))
    if not nearest_sizes:
        raise CropError("Candidate crop is too small to preserve the source aspect ratio.")
    nearest_size = max(nearest_sizes, key=lambda size: size[0] * size[1])
    if exact_size and exact_size[0] * exact_size[1] >= nearest_size[0] * nearest_size[1] * 0.995:
        crop_width, crop_height = exact_size
    else:
        crop_width, crop_height = nearest_size
    left += ((right - left) - crop_width) // 2
    top += ((bottom - top) - crop_height) // 2
    return left, top, left + crop_width, top + crop_height


def _aspect_ratio(width: int, height: int) -> str:
    divisor = math.gcd(width, height)
    return f"{width // divisor}:{height // divisor}"


def validate_source_aspect_box(
    box: dict[str, float], tolerance: float = ASPECT_TOLERANCE
) -> None:
    """Require equal normalized extents so the crop keeps the source aspect ratio."""
    normalized_width = float(box["right"]) - float(box["left"])
    normalized_height = float(box["bottom"]) - float(box["top"])
    if abs(normalized_width - normalized_height) > tolerance:
        raise CropError("Candidate crop must preserve the source aspect ratio.")


def render_crops(
    source: str | Path,
    manifest: str | Path,
    output_dir: str | Path,
    *,
    min_short_edge: int = 512,
    overwrite: bool = False,
    final_selection: bool = False,
) -> dict[str, Any]:
    """Validate a crop manifest and render lossless PNG crops."""
    if min_short_edge < 1:
        raise CropError("min_short_edge must be at least 1 pixel.")

    image, source_metadata = load_oriented_image(source)
    candidates = _read_manifest(Path(manifest))
    if final_selection:
        if len(candidates) != 1:
            raise CropError("A final selection must contain exactly one crop.")
        if candidates[0]["role"] != "unexpected":
            raise CropError("A final selection crop role must be unexpected.")
    output = Path(output_dir)
    crop_paths = [output / f"{item['id']}.png" for item in candidates]
    report_path = output / "render-manifest.json"
    existing = [path for path in [*crop_paths, report_path] if path.exists()]
    if existing and not overwrite:
        names = ", ".join(path.name for path in existing)
        raise CropError(f"Output already exists: {names}. Use --overwrite to replace it.")

    width, height = image.size
    planned: list[tuple[dict[str, Any], tuple[int, int, int, int], Path]] = []
    for item, crop_path in zip(candidates, crop_paths):
        validate_source_aspect_box(item["box"])
        pixels = _pixel_box(item["box"], width, height)
        crop_width = pixels[2] - pixels[0]
        crop_height = pixels[3] - pixels[1]
        area_fraction = (crop_width * crop_height) / (width * height)
        if area_fraction >= MAX_CROP_AREA_FRACTION:
            raise CropError(
                f"Candidate {item['id']} must use less than 50% of the source area; "
                f"got {area_fraction:.3%}."
            )
        if min(crop_width, crop_height) < min_short_edge:
            raise CropError(
                f"Candidate {item['id']} short edge is {min(crop_width, crop_height)}px; "
                f"minimum is {min_short_edge}px."
            )
        planned.append((item, pixels, crop_path))

    output.mkdir(parents=True, exist_ok=True)
    rendered_items = []
    icc_profile = source_metadata.pop("icc_profile")
    for item, pixels, crop_path in planned:
        cropped = image.crop(pixels)
        save_options = {"format": "PNG"}
        if icc_profile:
            save_options["icc_profile"] = icc_profile
        cropped.save(crop_path, **save_options)
        crop_width, crop_height = cropped.size
        source_area = width * height
        crop_area = crop_width * crop_height
        area_fraction = crop_area / source_area
        rendered_items.append(
            {
                "id": item["id"],
                "role": item["role"],
                "proposal_reason": item["proposal_reason"],
                "normalized_box": [
                    float(item["box"][key]) for key in ("left", "top", "right", "bottom")
                ],
                "pixel_box": list(pixels),
                "output_file": crop_path.name,
                "output_size": [crop_width, crop_height],
                "aspect_ratio": _aspect_ratio(crop_width, crop_height),
                "source_area_pixels": source_area,
                "crop_area_pixels": crop_area,
                "area_fraction": area_fraction,
                "resolution_recovery_required": area_fraction < RECOVERY_THRESHOLD,
                "resized": False,
            }
        )

    report = {
        "schema_version": SCHEMA_VERSION,
        "source": source_metadata,
        "rendering": {
            "output_format": "PNG",
            "exif_oriented_before_crop": True,
            "resized": False,
            "filters_applied": False,
            "generated_pixels": False,
            "final_selection": final_selection,
            "max_crop_area_fraction": MAX_CROP_AREA_FRACTION,
        },
        "crops": rendered_items,
    }
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Render exact PNG crops from normalized crop coordinates."
    )
    parser.add_argument("--source", required=True, type=Path, help="JPG, JPEG, PNG, or WebP source")
    parser.add_argument("--manifest", required=True, type=Path, help="Crop manifest JSON")
    parser.add_argument("--output-dir", required=True, type=Path, help="Directory for crops and report")
    parser.add_argument(
        "--min-short-edge",
        type=int,
        default=512,
        help="Reject crops whose shorter edge is below this pixel count (default: 512)",
    )
    parser.add_argument("--overwrite", action="store_true", help="Replace matching outputs")
    parser.add_argument(
        "--final-selection",
        action="store_true",
        help="Require exactly one crop with the unexpected role",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = render_crops(
            args.source,
            args.manifest,
            args.output_dir,
            min_short_edge=args.min_short_edge,
            overwrite=args.overwrite,
            final_selection=args.final_selection,
        )
    except CropError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
