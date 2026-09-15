import importlib.util
import inspect
import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "crop_photo.py"
PREPARE_MODULE_PATH = ROOT / "scripts" / "prepare_photo.py"


def load_module():
    if not MODULE_PATH.exists():
        raise AssertionError("scripts/crop_photo.py should exist")
    spec = importlib.util.spec_from_file_location("crop_photo", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def load_prepare_module():
    if not PREPARE_MODULE_PATH.exists():
        raise AssertionError("scripts/prepare_photo.py should exist")
    spec = importlib.util.spec_from_file_location("prepare_photo", PREPARE_MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def write_manifest(path: Path, candidates: list[dict]) -> None:
    path.write_text(
        json.dumps({"schema_version": "1.0", "candidates": candidates}),
        encoding="utf-8",
    )


def candidate(
    crop_id: str = "safe-01",
    role: str = "safe",
    left: float = 0.0,
    top: float = 0.0,
    right: float = 0.5,
    bottom: float = 0.5,
) -> dict:
    return {
        "id": crop_id,
        "role": role,
        "box": {"left": left, "top": top, "right": right, "bottom": bottom},
        "proposal_reason": "A deliberate frame.",
    }


class CropPhotoTests(unittest.TestCase):
    def test_rejects_crop_at_or_above_half_source_area(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.png"
            Image.new("RGB", (1000, 1000), "blue").save(source)

            below = root / "below.json"
            write_manifest(below, [candidate(right=0.70, bottom=0.70)])
            report = module.render_crops(
                source, below, root / "below-output", min_short_edge=100
            )
            self.assertLess(report["crops"][0]["area_fraction"], 0.50)

            at_or_above = root / "at-or-above.json"
            write_manifest(at_or_above, [candidate(right=0.71, bottom=0.71)])
            with self.assertRaisesRegex(module.CropError, "less than 50%"):
                module.render_crops(
                    source, at_or_above, root / "at-or-above-output", min_short_edge=100
                )

    def test_final_selection_requires_one_unexpected_crop(self):
        module = load_module()
        self.assertIn("final_selection", inspect.signature(module.render_crops).parameters)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.png"
            Image.new("RGB", (1000, 1000), "blue").save(source)

            multiple = root / "multiple.json"
            write_manifest(
                multiple,
                [candidate("crop-01", "unexpected"), candidate("crop-02", "unexpected", 0.5, 0.5, 1, 1)],
            )
            with self.assertRaisesRegex(module.CropError, "exactly one"):
                module.render_crops(
                    source,
                    multiple,
                    root / "multiple-output",
                    min_short_edge=100,
                    final_selection=True,
                )

            wrong_role = root / "wrong-role.json"
            write_manifest(wrong_role, [candidate("crop-01", "safe")])
            with self.assertRaisesRegex(module.CropError, "role must be unexpected"):
                module.render_crops(
                    source,
                    wrong_role,
                    root / "wrong-role-output",
                    min_short_edge=100,
                    final_selection=True,
                )

            valid = root / "valid.json"
            write_manifest(valid, [candidate("unexpected", "unexpected")])
            report = module.render_crops(
                source,
                valid,
                root / "valid-output",
                min_short_edge=100,
                final_selection=True,
            )
            self.assertTrue(report["rendering"]["final_selection"])
            self.assertEqual(report["rendering"]["max_crop_area_fraction"], 0.50)

    def test_prepare_writes_oriented_preview_and_metadata(self):
        module = load_prepare_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "rotated.jpg"
            image = Image.new("RGB", (40, 20), "red")
            exif = Image.Exif()
            exif[274] = 6
            image.save(source, exif=exif)

            report = module.prepare_photo(source, root / "prepared")

            with Image.open(root / "prepared" / "source-oriented.png") as preview:
                preview_size = preview.size
            metadata = json.loads((root / "prepared" / "source-metadata.json").read_text())
            self.assertEqual(preview_size, (20, 40))
            self.assertEqual(metadata, report)
            self.assertEqual(metadata["oriented_size"], [20, 40])
            self.assertTrue(metadata["exif_orientation_applied"])

    def test_prepare_refuses_overwrite_by_default(self):
        module = load_prepare_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.png"
            Image.new("RGB", (800, 800)).save(source)
            module.prepare_photo(source, root / "prepared")

            with self.assertRaisesRegex(module.CropError, "already exists"):
                module.prepare_photo(source, root / "prepared")

    def test_declares_the_four_approved_extensions(self):
        module = load_module()
        self.assertEqual(module.SUPPORTED_EXTENSIONS, {".jpg", ".jpeg", ".png", ".webp"})

    def test_load_applies_exif_orientation_before_cropping(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "rotated.jpg"
            image = Image.new("RGB", (40, 20), "red")
            exif = Image.Exif()
            exif[274] = 6
            image.save(source, exif=exif)

            loaded, metadata = module.load_oriented_image(source)

            self.assertEqual(loaded.size, (20, 40))
            self.assertTrue(metadata["exif_orientation_applied"])

    def test_renders_exact_png_crop_without_resizing_or_recoloring(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.png"
            manifest = root / "crops.json"
            output = root / "out"
            image = Image.new("RGB", (1200, 800))
            for x in range(1200):
                for y in range(800):
                    image.putpixel((x, y), (x % 256, y % 256, (x + y) % 256))
            image.save(source)
            write_manifest(manifest, [candidate()])

            report = module.render_crops(source, manifest, output, min_short_edge=400)
            rendered = Image.open(output / "safe-01.png")

            self.assertEqual(rendered.size, (600, 400))
            self.assertEqual(rendered.getpixel((123, 300)), image.getpixel((123, 300)))
            self.assertEqual(report["crops"][0]["pixel_box"], [0, 0, 600, 400])
            self.assertFalse(report["crops"][0]["resized"])

    def test_accepts_source_aspect_crop_and_reports_area_fraction(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.png"
            manifest = root / "crops.json"
            output = root / "out"
            Image.new("RGB", (1200, 800), "blue").save(source)
            write_manifest(manifest, [candidate(left=0.1, top=0.2, right=0.6, bottom=0.7)])

            report = module.render_crops(source, manifest, output, min_short_edge=100)

            crop = report["crops"][0]
            self.assertEqual(crop["source_area_pixels"], 960000)
            self.assertEqual(crop["crop_area_pixels"], 240000)
            self.assertEqual(crop["area_fraction"], 0.25)
            self.assertFalse(crop["resolution_recovery_required"])

    def test_pixel_rounding_still_preserves_exact_source_aspect_ratio(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.png"
            manifest = root / "crops.json"
            output = root / "out"
            Image.new("RGB", (1152, 1536), "blue").save(source)
            write_manifest(
                manifest,
                [candidate(left=0.10, top=0.10, right=0.60, bottom=0.60)],
            )

            report = module.render_crops(source, manifest, output, min_short_edge=100)

            crop = report["crops"][0]
            self.assertEqual(crop["pixel_box"], [115, 153, 691, 921])
            self.assertEqual(crop["output_size"], [576, 768])
            self.assertEqual(crop["output_size"][0] * 1536, crop["output_size"][1] * 1152)

    def test_coprime_source_dimensions_use_nearest_pixel_aspect(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.png"
            manifest = root / "crops.json"
            output = root / "out"
            Image.new("RGB", (1279, 1705), "blue").save(source)
            write_manifest(
                manifest,
                [candidate(left=0.1, top=0.1, right=0.7, bottom=0.7)],
            )

            report = module.render_crops(source, manifest, output, min_short_edge=100)

            crop = report["crops"][0]
            self.assertEqual(crop["output_size"], [768, 1024])
            width_error = abs(crop["output_size"][0] - crop["output_size"][1] * 1279 / 1705)
            self.assertLess(width_error, 0.5)

    def test_rejects_crop_that_changes_source_aspect_ratio(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.png"
            manifest = root / "crops.json"
            output = root / "out"
            Image.new("RGB", (1200, 800), "blue").save(source)
            write_manifest(manifest, [candidate(left=0.1, top=0.2, right=0.7, bottom=0.7)])

            with self.assertRaisesRegex(module.CropError, "source aspect ratio"):
                module.render_crops(source, manifest, output, min_short_edge=100)

            self.assertFalse(output.exists())

    def test_resolution_recovery_uses_strict_twenty_percent_boundary(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.png"
            Image.new("RGB", (1000, 1000), "blue").save(source)

            at_manifest = root / "at.json"
            side = 0.4472135955
            write_manifest(at_manifest, [candidate(right=side, bottom=side)])
            at_report = module.render_crops(
                source, at_manifest, root / "at-output", min_short_edge=100
            )
            self.assertGreaterEqual(at_report["crops"][0]["area_fraction"], 0.20)
            self.assertFalse(at_report["crops"][0]["resolution_recovery_required"])

            below_manifest = root / "below.json"
            write_manifest(below_manifest, [candidate(right=0.44, bottom=0.44)])
            below_report = module.render_crops(
                source, below_manifest, root / "below-output", min_short_edge=100
            )
            self.assertLess(below_report["crops"][0]["area_fraction"], 0.20)
            self.assertTrue(below_report["crops"][0]["resolution_recovery_required"])

    def test_preserves_png_alpha_channel(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.png"
            manifest = root / "crops.json"
            output = root / "out"
            Image.new("RGBA", (800, 800), (10, 20, 30, 40)).save(source)
            write_manifest(manifest, [candidate(right=0.5, bottom=0.5)])

            module.render_crops(source, manifest, output, min_short_edge=400)

            rendered = Image.open(output / "safe-01.png")
            self.assertEqual(rendered.mode, "RGBA")
            self.assertEqual(rendered.getpixel((10, 10)), (10, 20, 30, 40))

    def test_accepts_jpg_jpeg_png_and_webp(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            formats = [("jpg", "JPEG"), ("jpeg", "JPEG"), ("png", "PNG"), ("webp", "WEBP")]
            for extension, image_format in formats:
                source = root / f"source.{extension}"
                Image.new("RGB", (800, 800), "blue").save(source, format=image_format)
                manifest = root / f"{extension}.json"
                output = root / extension
                write_manifest(manifest, [candidate(right=0.5, bottom=0.5)])
                report = module.render_crops(source, manifest, output, min_short_edge=400)
                self.assertEqual(len(report["crops"]), 1)

    def test_rejects_unsupported_extension(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.bmp"
            manifest = root / "crops.json"
            Image.new("RGB", (800, 800)).save(source)
            write_manifest(manifest, [candidate(right=0.5, bottom=0.5)])

            with self.assertRaisesRegex(module.CropError, "Unsupported image extension"):
                module.render_crops(source, manifest, root / "out", min_short_edge=400)

    def test_rejects_mislabeled_image_format(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.jpg"
            manifest = root / "crops.json"
            Image.new("RGB", (800, 800)).save(source, format="PNG")
            write_manifest(manifest, [candidate(right=1.0)])

            with self.assertRaisesRegex(module.CropError, "does not match its extension"):
                module.render_crops(source, manifest, root / "out", min_short_edge=400)

    def test_rejects_out_of_range_box(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.png"
            manifest = root / "crops.json"
            Image.new("RGB", (800, 800)).save(source)
            write_manifest(manifest, [candidate(left=-0.1, right=1.0)])

            with self.assertRaisesRegex(module.CropError, "between 0 and 1"):
                module.render_crops(source, manifest, root / "out", min_short_edge=100)

    def test_rejects_unsafe_or_duplicate_candidate_ids(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.png"
            manifest = root / "crops.json"
            Image.new("RGB", (800, 800)).save(source)

            write_manifest(manifest, [candidate("../escape", right=1.0)])
            with self.assertRaisesRegex(module.CropError, "safe lowercase slug"):
                module.render_crops(source, manifest, root / "unsafe", min_short_edge=100)

            write_manifest(manifest, [candidate("safe-01", right=1.0), candidate("safe-01", right=1.0)])
            with self.assertRaisesRegex(module.CropError, "Duplicate candidate id"):
                module.render_crops(source, manifest, root / "duplicate", min_short_edge=100)

    def test_rejects_crop_below_minimum_short_edge(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.png"
            manifest = root / "crops.json"
            Image.new("RGB", (1000, 1000)).save(source)
            write_manifest(manifest, [candidate(right=0.2, bottom=0.2)])

            with self.assertRaisesRegex(module.CropError, "short edge"):
                module.render_crops(source, manifest, root / "out", min_short_edge=512)

    def test_refuses_to_overwrite_existing_crop_by_default(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.png"
            manifest = root / "crops.json"
            output = root / "out"
            Image.new("RGB", (800, 800)).save(source)
            write_manifest(manifest, [candidate(right=0.5, bottom=0.5)])
            module.render_crops(source, manifest, output, min_short_edge=400)

            with self.assertRaisesRegex(module.CropError, "already exists"):
                module.render_crops(source, manifest, output, min_short_edge=400)

    def test_writes_reproducible_render_manifest(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.png"
            manifest = root / "crops.json"
            output = root / "out"
            Image.new("RGB", (1000, 800), "green").save(source)
            write_manifest(manifest, [candidate("unexpected", "unexpected", 0.1, 0.1, 0.7, 0.7)])

            report = module.render_crops(source, manifest, output, min_short_edge=400)
            on_disk = json.loads((output / "render-manifest.json").read_text(encoding="utf-8"))

            self.assertEqual(on_disk, report)
            self.assertEqual(on_disk["schema_version"], "1.0")
            self.assertEqual(on_disk["source"]["oriented_size"], [1000, 800])
            self.assertEqual(on_disk["crops"][0]["role"], "unexpected")
            self.assertEqual(on_disk["crops"][0]["aspect_ratio"], "5:4")


if __name__ == "__main__":
    unittest.main()
