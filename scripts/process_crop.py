#!/usr/bin/env python3
"""Conditionally recover resolution and gently enhance final raw crops."""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image, ImageEnhance, ImageFilter, UnidentifiedImageError


SCHEMA_VERSION = "1.0"
RECOVERY_THRESHOLD = 0.20
WHITE_BALANCE_GAIN_BOUNDS = (0.97, 1.03)
WHITE_BALANCE_NEUTRAL_CHROMA_LIMIT = 0.18
WHITE_BALANCE_MIN_NEUTRAL_FRACTION = 0.01
CONTRAST_FACTOR = 1.03
COLOR_FACTOR = 1.02
SHARPNESS_FACTOR = 1.10
UNSHARP_MASK = {"radius": 1.2, "percent": 90, "threshold": 3}
MAX_ROTATION_DEGREES = 5.0
MAX_PERSPECTIVE_DISPLACEMENT = 0.08
MAX_INPAINT_AREA_FRACTION = 0.01
CANONICAL_CORNERS = ((0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0))
SAFE_ID = re.compile(r"^[a-z0-9](?:[a-z0-9_-]{0,62}[a-z0-9])?$")


class ProcessError(ValueError):
    """Raised when crop processing inputs are invalid or unsafe."""


def _read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ProcessError(f"{label} is missing: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ProcessError(f"{label} is not valid JSON: {exc.msg}") from exc
    if not isinstance(payload, dict):
        raise ProcessError(f"{label} must contain a JSON object.")
    return payload


def _size(value: Any, label: str) -> tuple[int, int]:
    if (
        not isinstance(value, list)
        or len(value) != 2
        or any(isinstance(item, bool) or not isinstance(item, int) or item < 1 for item in value)
    ):
        raise ProcessError(f"{label} must contain two positive integer dimensions.")
    return value[0], value[1]


def _load_render_job(render_manifest: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    payload = _read_json(render_manifest, "Render manifest")
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ProcessError(f"Render manifest schema_version must be '{SCHEMA_VERSION}'.")

    source = payload.get("source")
    if not isinstance(source, dict):
        raise ProcessError("Render manifest requires a source object.")
    source_size = _size(source.get("oriented_size"), "source.oriented_size")

    crops = payload.get("crops")
    if not isinstance(crops, list):
        raise ProcessError("Render manifest crops must be an array.")

    seen: set[str] = set()
    validated: list[dict[str, Any]] = []
    for index, item in enumerate(crops):
        if not isinstance(item, dict):
            raise ProcessError(f"Crop {index} must be an object.")
        crop_id = item.get("id")
        if not isinstance(crop_id, str) or not SAFE_ID.fullmatch(crop_id):
            raise ProcessError(f"Crop {index} id must be a safe lowercase slug.")
        if crop_id in seen:
            raise ProcessError(f"Duplicate crop id: {crop_id}")
        seen.add(crop_id)

        output_file = item.get("output_file")
        if (
            not isinstance(output_file, str)
            or Path(output_file).name != output_file
            or Path(output_file).suffix.lower() != ".png"
        ):
            raise ProcessError(f"Crop {crop_id} output_file must be a local PNG filename.")
        raw_size = _size(item.get("output_size"), f"Crop {crop_id} output_size")

        area_fraction = item.get("area_fraction")
        if (
            isinstance(area_fraction, bool)
            or not isinstance(area_fraction, (int, float))
            or not math.isfinite(float(area_fraction))
            or not 0 < float(area_fraction) <= 1
        ):
            raise ProcessError(f"Crop {crop_id} area_fraction must be between 0 and 1.")
        area_fraction = float(area_fraction)
        recovery_required = item.get("resolution_recovery_required")
        if not isinstance(recovery_required, bool):
            raise ProcessError(f"Crop {crop_id} requires resolution_recovery_required.")
        if recovery_required != (area_fraction < RECOVERY_THRESHOLD):
            raise ProcessError(f"Crop {crop_id} has an inconsistent recovery trigger.")

        raw_path = render_manifest.parent / output_file
        if not raw_path.is_file():
            raise ProcessError(f"Raw crop is missing: {output_file}")
        try:
            with Image.open(raw_path) as opened:
                actual_size = opened.size
                opened.verify()
        except (UnidentifiedImageError, OSError) as exc:
            raise ProcessError(f"Could not decode raw crop: {output_file}") from exc
        if actual_size != raw_size:
            raise ProcessError(
                f"Raw crop {output_file} dimensions {actual_size} do not match manifest {raw_size}."
            )

        validated.append(
            {
                "id": crop_id,
                "raw_path": raw_path,
                "raw_file": output_file,
                "raw_size": raw_size,
                "area_fraction": area_fraction,
                "resolution_recovery_required": recovery_required,
            }
        )
    return {"source_size": source_size}, validated


def _finite_number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ProcessError(f"{label} must be a finite number.")
    number = float(value)
    if not math.isfinite(number):
        raise ProcessError(f"{label} must be a finite number.")
    return number


def _normalized_point(value: Any, label: str) -> list[float]:
    if not isinstance(value, list) or len(value) != 2:
        raise ProcessError(f"{label} must contain two normalized coordinates.")
    point = [_finite_number(coordinate, label) for coordinate in value]
    if any(coordinate < 0 or coordinate > 1 for coordinate in point):
        raise ProcessError(f"{label} coordinates must be between 0 and 1.")
    return point


def _polygon_area(points: list[list[float]]) -> float:
    return abs(
        sum(
            points[index][0] * points[(index + 1) % len(points)][1]
            - points[(index + 1) % len(points)][0] * points[index][1]
            for index in range(len(points))
        )
    ) / 2


def _load_corrections(path: Path | None, crop_ids: set[str]) -> dict[str, dict[str, Any]]:
    if path is None:
        return {}
    payload = _read_json(path, "Correction manifest")
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ProcessError(f"Correction manifest schema_version must be '{SCHEMA_VERSION}'.")
    items = payload.get("corrections")
    if not isinstance(items, list):
        raise ProcessError("Correction manifest corrections must be an array.")

    corrections: dict[str, dict[str, Any]] = {}
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise ProcessError(f"Correction {index} must be an object.")
        crop_id = item.get("id")
        if not isinstance(crop_id, str) or not SAFE_ID.fullmatch(crop_id):
            raise ProcessError(f"Correction {index} id must be a safe lowercase slug.")
        if crop_id in corrections:
            raise ProcessError(f"Duplicate correction id: {crop_id}")
        if crop_id not in crop_ids:
            raise ProcessError(f"Correction references unknown crop: {crop_id}")

        rotation = _finite_number(item.get("rotation_degrees", 0.0), "rotation_degrees")
        if abs(rotation) > MAX_ROTATION_DEGREES:
            raise ProcessError("Correction rotation must not exceed 5 degrees.")

        perspective_value = item.get("perspective_corners")
        perspective: list[list[float]] | None = None
        if perspective_value is not None:
            if not isinstance(perspective_value, list) or len(perspective_value) != 4:
                raise ProcessError("perspective_corners must contain exactly four points.")
            perspective = [
                _normalized_point(point, f"perspective_corners[{point_index}]")
                for point_index, point in enumerate(perspective_value)
            ]
            for point, canonical in zip(perspective, CANONICAL_CORNERS):
                if any(
                    abs(coordinate - expected) > MAX_PERSPECTIVE_DISPLACEMENT
                    for coordinate, expected in zip(point, canonical)
                ):
                    raise ProcessError("Perspective displacement must not exceed 8% per axis.")

        polygons_value = item.get("inpaint_polygons", [])
        if not isinstance(polygons_value, list):
            raise ProcessError("inpaint_polygons must be an array.")
        polygons: list[list[list[float]]] = []
        for polygon_index, polygon_value in enumerate(polygons_value):
            if not isinstance(polygon_value, list) or len(polygon_value) < 3:
                raise ProcessError("Each inpaint polygon requires at least three points.")
            polygon = [
                _normalized_point(point, f"inpaint_polygons[{polygon_index}][{point_index}]")
                for point_index, point in enumerate(polygon_value)
            ]
            if _polygon_area(polygon) <= 0:
                raise ProcessError("Each inpaint polygon must have positive area.")
            polygons.append(polygon)
        inpaint_area = sum(_polygon_area(polygon) for polygon in polygons)
        if inpaint_area > MAX_INPAINT_AREA_FRACTION:
            raise ProcessError("Combined inpaint area must not exceed 1% of the crop.")
        if abs(rotation) < 1e-9 and perspective is None and not polygons:
            raise ProcessError(f"Correction {crop_id} does not request an operation.")

        corrections[crop_id] = {
            "rotation_degrees": rotation,
            "perspective_corners": perspective,
            "inpaint_polygons": polygons,
            "inpainted_area_fraction": inpaint_area,
        }
    return corrections


def _pil_from_array(array: np.ndarray, mode: str) -> Image.Image:
    converted = Image.fromarray(array)
    return converted.convert(mode) if converted.mode != mode else converted


def _apply_perspective(image: Image.Image, corners: list[list[float]] | None) -> Image.Image:
    if corners is None:
        return image
    working = image.convert("RGBA" if "A" in image.getbands() else "RGB")
    array = np.asarray(working)
    height, width = array.shape[:2]
    source_points = np.float32(
        [[point[0] * (width - 1), point[1] * (height - 1)] for point in corners]
    )
    destination_points = np.float32(
        [[0, 0], [width - 1, 0], [width - 1, height - 1], [0, height - 1]]
    )
    matrix = cv2.getPerspectiveTransform(source_points, destination_points)
    warped = cv2.warpPerspective(
        array,
        matrix,
        (width, height),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_REFLECT_101,
    )
    return _pil_from_array(warped, working.mode)


def _largest_centered_crop_inside_polygon(
    polygon: np.ndarray, canvas_size: tuple[int, int], source_size: tuple[int, int]
) -> tuple[int, int, int, int]:
    canvas_width, canvas_height = canvas_size
    source_width, source_height = source_size
    center_x, center_y = canvas_width / 2, canvas_height / 2

    def fits(scale: float) -> bool:
        half_width = source_width * scale / 2
        half_height = source_height * scale / 2
        corners = (
            (center_x - half_width, center_y - half_height),
            (center_x + half_width, center_y - half_height),
            (center_x + half_width, center_y + half_height),
            (center_x - half_width, center_y + half_height),
        )
        return all(cv2.pointPolygonTest(polygon, point, False) >= 0 for point in corners)

    low, high = 0.0, 1.0
    for _ in range(40):
        middle = (low + high) / 2
        if fits(middle):
            low = middle
        else:
            high = middle
    crop_width = max(1, math.floor(source_width * low))
    crop_height = max(1, math.floor(source_height * low))
    left = round(center_x - crop_width / 2)
    top = round(center_y - crop_height / 2)
    return left, top, left + crop_width, top + crop_height


def _apply_rotation(image: Image.Image, degrees: float) -> Image.Image:
    if abs(degrees) < 1e-9:
        return image
    working = image.convert("RGBA" if "A" in image.getbands() else "RGB")
    array = np.asarray(working)
    height, width = array.shape[:2]
    center = (width / 2, height / 2)
    matrix = cv2.getRotationMatrix2D(center, degrees, 1.0)
    cosine = abs(matrix[0, 0])
    sine = abs(matrix[0, 1])
    canvas_width = math.ceil(height * sine + width * cosine)
    canvas_height = math.ceil(height * cosine + width * sine)
    matrix[0, 2] += canvas_width / 2 - center[0]
    matrix[1, 2] += canvas_height / 2 - center[1]
    border_value = (0, 0, 0, 0) if working.mode == "RGBA" else (0, 0, 0)
    rotated = cv2.warpAffine(
        array,
        matrix,
        (canvas_width, canvas_height),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=border_value,
    )
    original_corners = np.float32([[[0, 0], [width, 0], [width, height], [0, height]]])
    polygon = cv2.transform(original_corners, matrix)[0]
    crop_box = _largest_centered_crop_inside_polygon(
        polygon, (canvas_width, canvas_height), (width, height)
    )
    return _pil_from_array(rotated, working.mode).crop(crop_box)


def apply_local_inpaint(
    image: Image.Image, polygons: list[list[list[float]]]
) -> Image.Image:
    """Inpaint only the explicitly supplied normalized polygon regions."""
    if not polygons:
        return image
    has_alpha = "A" in image.getbands()
    rgb = np.asarray(image.convert("RGB"))
    height, width = rgb.shape[:2]
    mask = np.zeros((height, width), dtype=np.uint8)
    pixel_polygons = []
    for polygon in polygons:
        points = np.array(
            [[round(x * (width - 1)), round(y * (height - 1))] for x, y in polygon],
            dtype=np.int32,
        )
        pixel_polygons.append(points)
    cv2.fillPoly(mask, pixel_polygons, 255)
    bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    repaired_bgr = cv2.inpaint(bgr, mask, 3, cv2.INPAINT_TELEA)
    repaired = Image.fromarray(cv2.cvtColor(repaired_bgr, cv2.COLOR_BGR2RGB))
    if has_alpha:
        repaired.putalpha(image.getchannel("A"))
    return repaired


def _apply_correction(image: Image.Image, correction: dict[str, Any]) -> Image.Image:
    corrected = _apply_perspective(image, correction["perspective_corners"])
    corrected = _apply_rotation(corrected, correction["rotation_degrees"])
    corrected = apply_local_inpaint(corrected, correction["inpaint_polygons"])
    return corrected


def _bounded_white_balance(image: Image.Image) -> tuple[Image.Image, list[float]]:
    array = np.asarray(image.convert("RGB"), dtype=np.float32)
    channel_mean = array.mean(axis=2)
    channel_spread = array.max(axis=2) - array.min(axis=2)
    neutral_mask = (
        (channel_mean >= 24)
        & (channel_mean <= 232)
        & (channel_spread / np.maximum(channel_mean, 1.0) <= WHITE_BALANCE_NEUTRAL_CHROMA_LIMIT)
    )
    neutral_count = int(neutral_mask.sum())
    minimum_count = max(64, math.ceil(array.shape[0] * array.shape[1] * WHITE_BALANCE_MIN_NEUTRAL_FRACTION))
    if neutral_count < minimum_count:
        return image.convert("RGB"), [1.0, 1.0, 1.0]

    means = [float(value) for value in array[neutral_mask].mean(axis=0)]
    target = sum(means) / 3
    lower, upper = WHITE_BALANCE_GAIN_BOUNDS
    gains = [max(lower, min(upper, target / value if value > 0 else 1.0)) for value in means]
    balanced_bands = []
    for band, gain in zip(image.split()[:3], gains):
        lookup = [min(255, max(0, round(value * gain))) for value in range(256)]
        balanced_bands.append(band.point(lookup))
    return Image.merge("RGB", balanced_bands), gains


def _enhance(raw: Image.Image, target_size: tuple[int, int]) -> tuple[Image.Image, list[float]]:
    has_alpha = "A" in raw.getbands()
    alpha = raw.getchannel("A") if has_alpha else None
    rgb = raw.convert("RGB").resize(target_size, Image.Resampling.LANCZOS)
    balanced, gains = _bounded_white_balance(rgb)
    enhanced = ImageEnhance.Contrast(balanced).enhance(CONTRAST_FACTOR)
    enhanced = ImageEnhance.Color(enhanced).enhance(COLOR_FACTOR)
    enhanced = enhanced.filter(ImageFilter.UnsharpMask(**UNSHARP_MASK))
    enhanced = ImageEnhance.Sharpness(enhanced).enhance(SHARPNESS_FACTOR)
    if alpha is not None:
        resized_alpha = alpha.resize(target_size, Image.Resampling.LANCZOS)
        enhanced.putalpha(resized_alpha)
    return enhanced, gains


def process_crops(
    render_manifest: str | Path,
    output_dir: str | Path,
    corrections: str | Path | None = None,
    *,
    overwrite: bool = False,
) -> dict[str, Any]:
    """Process only crops that require resolution recovery or approved correction."""
    manifest_path = Path(render_manifest)
    job, crops = _load_render_job(manifest_path)
    correction_map = _load_corrections(
        Path(corrections) if corrections is not None else None,
        {item["id"] for item in crops},
    )
    selected = [
        item
        for item in crops
        if item["resolution_recovery_required"] or item["id"] in correction_map
    ]
    output = Path(output_dir)
    output_paths = [output / f"{item['id']}-processed.png" for item in selected]
    report_path = output / "processing-manifest.json"
    existing = [path for path in [*output_paths, report_path] if path.exists()]
    if existing and not overwrite:
        names = ", ".join(path.name for path in existing)
        raise ProcessError(f"Output already exists: {names}. Use --overwrite to replace it.")

    output.mkdir(parents=True, exist_ok=True)
    items: list[dict[str, Any]] = []
    for item, processed_path in zip(selected, output_paths):
        with Image.open(item["raw_path"]) as opened:
            raw = opened.copy()
            icc_profile = opened.info.get("icc_profile")
        correction = correction_map.get(item["id"])
        working = _apply_correction(raw, correction) if correction else raw
        target_size = job["source_size"] if item["resolution_recovery_required"] else item["raw_size"]
        processed, gains = _enhance(working, target_size)
        save_options: dict[str, Any] = {"format": "PNG"}
        if icc_profile:
            save_options["icc_profile"] = icc_profile
        processed.save(processed_path, **save_options)
        triggers = []
        if item["resolution_recovery_required"]:
            triggers.append("resolution_recovery")
        if correction:
            triggers.append("gentle_correction")
        items.append(
            {
                "id": item["id"],
                "raw_file": item["raw_file"],
                "raw_size": list(item["raw_size"]),
                "area_fraction": item["area_fraction"],
                "trigger": triggers,
                "processed_file": processed_path.name,
                "target_size": list(target_size),
                "rotation_degrees": correction["rotation_degrees"] if correction else 0.0,
                "perspective_corners": correction["perspective_corners"] if correction else None,
                "inpaint_polygons": correction["inpaint_polygons"] if correction else [],
                "geometry_crop_applied": bool(
                    correction and abs(correction["rotation_degrees"]) >= 1e-9
                ),
                "geometry_intermediate_size": list(working.size),
                "white_balance_gains": gains,
                "synthetic_content": False,
                "interpolated_pixels": True,
                "color_adjustments_applied": True,
                "inpainted_area_fraction": (
                    correction["inpainted_area_fraction"] if correction else 0.0
                ),
            }
        )

    report = {
        "schema_version": SCHEMA_VERSION,
        "source_oriented_size": list(job["source_size"]),
        "processing": {
            "resize_method": "LANCZOS",
            "recovery_threshold": RECOVERY_THRESHOLD,
            "white_balance_gain_bounds": list(WHITE_BALANCE_GAIN_BOUNDS),
            "white_balance_method": "neutral-pixel bounded gain",
            "contrast_factor": CONTRAST_FACTOR,
            "color_factor": COLOR_FACTOR,
            "sharpness_factor": SHARPNESS_FACTOR,
            "unsharp_mask": UNSHARP_MASK,
            "network_used": False,
        },
        "items": items,
    }
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Conditionally recover resolution and gently enhance final raw crops."
    )
    parser.add_argument("--render-manifest", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--corrections", type=Path)
    parser.add_argument("--overwrite", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = process_crops(
            args.render_manifest,
            args.output_dir,
            args.corrections,
            overwrite=args.overwrite,
        )
    except ProcessError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
