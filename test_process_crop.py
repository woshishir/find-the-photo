import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "process_crop.py"


def load_module():
    if not MODULE_PATH.exists():
        raise AssertionError("scripts/process_crop.py should exist")
    spec = importlib.util.spec_from_file_location("process_crop", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_render_fixture(
    root: Path,
    *,
    source_size: tuple[int, int] = (1200, 800),
    raw_size: tuple[int, int] = (480, 320),
    area_fraction: float = 0.16,
    recovery_required: bool = True,
    mode: str = "RGB",
) -> tuple[Path, Path]:
    render_dir = root / "render"
    render_dir.mkdir()
    raw_path = render_dir / "crop-01.png"
    if mode == "RGBA":
        image = Image.new(mode, raw_size, (80, 120, 160, 96))
    else:
        image = Image.new(mode, raw_size, (80, 120, 160))
    image.save(raw_path)
    manifest = {
        "schema_version": "1.0",
        "source": {"oriented_size": list(source_size)},
        "rendering": {
            "output_format": "PNG",
            "resized": False,
            "filters_applied": False,
            "generated_pixels": False,
        },
        "crops": [
            {
                "id": "crop-01",
                "output_file": raw_path.name,
                "output_size": list(raw_size),
                "area_fraction": area_fraction,
                "resolution_recovery_required": recovery_required,
            }
        ],
    }
    manifest_path = render_dir / "render-manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    return manifest_path, raw_path


def write_corrections(path: Path, items: list[dict]) -> None:
    path.write_text(
        json.dumps({"schema_version": "1.0", "corrections": items}),
        encoding="utf-8",
    )


class ProcessCropTests(unittest.TestCase):
    def test_sub_20_percent_crop_is_processed_to_source_dimensions(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            render_manifest, raw_path = write_render_fixture(root)
            before_hash = sha256(raw_path)

            report = module.process_crops(render_manifest, root / "processed")

            processed_path = root / "processed" / "crop-01-processed.png"
            with Image.open(processed_path) as result:
                self.assertEqual(result.size, (1200, 800))
            self.assertEqual(sha256(raw_path), before_hash)
            self.assertEqual(report["items"][0]["trigger"], ["resolution_recovery"])
            self.assertEqual(report["items"][0]["target_size"], [1200, 800])
            self.assertTrue(report["items"][0]["interpolated_pixels"])
            self.assertFalse(report["items"][0]["synthetic_content"])

    def test_crop_at_or_above_20_percent_without_correction_is_skipped(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            render_manifest, _ = write_render_fixture(
                root,
                raw_size=(600, 400),
                area_fraction=0.25,
                recovery_required=False,
            )

            report = module.process_crops(render_manifest, root / "processed")

            self.assertEqual(report["items"], [])
            self.assertFalse((root / "processed" / "crop-01-processed.png").exists())

    def test_rejects_missing_raw_crop_before_writing_output(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            render_manifest, raw_path = write_render_fixture(root)
            raw_path.unlink()
            output = root / "processed"

            with self.assertRaisesRegex(module.ProcessError, "missing"):
                module.process_crops(render_manifest, output)

            self.assertFalse(output.exists())

    def test_rejects_raw_size_mismatch_before_writing_output(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            render_manifest, raw_path = write_render_fixture(root)
            Image.new("RGB", (479, 320), "red").save(raw_path)
            output = root / "processed"

            with self.assertRaisesRegex(module.ProcessError, "dimensions"):
                module.process_crops(render_manifest, output)

            self.assertFalse(output.exists())

    def test_preserves_alpha_during_resolution_recovery(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            render_manifest, _ = write_render_fixture(root, mode="RGBA")

            module.process_crops(render_manifest, root / "processed")

            with Image.open(root / "processed" / "crop-01-processed.png") as result:
                self.assertEqual(result.mode, "RGBA")
                self.assertEqual(result.getchannel("A").getextrema(), (96, 96))

    def test_refuses_to_overwrite_processed_output_by_default(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            render_manifest, _ = write_render_fixture(root)
            output = root / "processed"
            module.process_crops(render_manifest, output)

            with self.assertRaisesRegex(module.ProcessError, "already exists"):
                module.process_crops(render_manifest, output)

    def test_writes_reproducible_processing_manifest(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            render_manifest, _ = write_render_fixture(root)
            output = root / "processed"

            report = module.process_crops(render_manifest, output)
            on_disk = json.loads((output / "processing-manifest.json").read_text())

            self.assertEqual(on_disk, report)
            self.assertEqual(on_disk["schema_version"], "1.0")
            self.assertEqual(on_disk["processing"]["resize_method"], "LANCZOS")
            self.assertEqual(on_disk["processing"]["white_balance_gain_bounds"], [0.97, 1.03])

    def test_white_balance_ignores_dominant_subject_color(self):
        module = load_module()
        image = Image.new("RGB", (200, 200), (190, 45, 45))
        for x in range(80, 120):
            for y in range(80, 120):
                image.putpixel((x, y), (128, 128, 128))

        balanced, gains = module._bounded_white_balance(image)

        self.assertEqual(gains, [1.0, 1.0, 1.0])
        self.assertEqual(balanced.getpixel((100, 100)), (128, 128, 128))

    def test_rejects_rotation_beyond_limit(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            render_manifest, _ = write_render_fixture(root)
            corrections = root / "corrections.json"
            write_corrections(
                corrections,
                [{"id": "crop-01", "rotation_degrees": 5.01}],
            )

            with self.assertRaisesRegex(module.ProcessError, "5 degrees"):
                module.process_crops(render_manifest, root / "processed", corrections)

            self.assertFalse((root / "processed").exists())

    def test_rejects_perspective_beyond_limit(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            render_manifest, _ = write_render_fixture(root)
            corrections = root / "corrections.json"
            write_corrections(
                corrections,
                [
                    {
                        "id": "crop-01",
                        "perspective_corners": [
                            [0.09, 0.0],
                            [1.0, 0.0],
                            [1.0, 1.0],
                            [0.0, 1.0],
                        ],
                    }
                ],
            )

            with self.assertRaisesRegex(module.ProcessError, "8%"):
                module.process_crops(render_manifest, root / "processed", corrections)

            self.assertFalse((root / "processed").exists())

    def test_rejects_inpaint_area_beyond_limit(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            render_manifest, _ = write_render_fixture(root)
            corrections = root / "corrections.json"
            write_corrections(
                corrections,
                [
                    {
                        "id": "crop-01",
                        "inpaint_polygons": [
                            [[0.10, 0.10], [0.21, 0.10], [0.21, 0.21], [0.10, 0.21]]
                        ],
                    }
                ],
            )

            with self.assertRaisesRegex(module.ProcessError, "1%"):
                module.process_crops(render_manifest, root / "processed", corrections)

            self.assertFalse((root / "processed").exists())

    def test_rejects_duplicate_and_unknown_correction_ids(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            render_manifest, _ = write_render_fixture(root)
            duplicate = root / "duplicate.json"
            write_corrections(
                duplicate,
                [
                    {"id": "crop-01", "rotation_degrees": 1.0},
                    {"id": "crop-01", "rotation_degrees": 2.0},
                ],
            )
            with self.assertRaisesRegex(module.ProcessError, "Duplicate correction id"):
                module.process_crops(render_manifest, root / "duplicate-output", duplicate)

            unknown = root / "unknown.json"
            write_corrections(unknown, [{"id": "crop-99", "rotation_degrees": 1.0}])
            with self.assertRaisesRegex(module.ProcessError, "unknown crop"):
                module.process_crops(render_manifest, root / "unknown-output", unknown)

    def test_rejects_malformed_inpaint_polygon(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            render_manifest, _ = write_render_fixture(root)
            corrections = root / "corrections.json"
            write_corrections(
                corrections,
                [{"id": "crop-01", "inpaint_polygons": [[[0.1, 0.1], [0.2, 0.2]]]}],
            )

            with self.assertRaisesRegex(module.ProcessError, "at least three points"):
                module.process_crops(render_manifest, root / "processed", corrections)

    def test_correction_only_output_keeps_raw_dimensions_and_aspect(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            render_manifest, _ = write_render_fixture(
                root,
                raw_size=(600, 400),
                area_fraction=0.25,
                recovery_required=False,
            )
            corrections = root / "corrections.json"
            write_corrections(corrections, [{"id": "crop-01", "rotation_degrees": 2.0}])

            report = module.process_crops(render_manifest, root / "processed", corrections)

            with Image.open(root / "processed" / "crop-01-processed.png") as result:
                self.assertEqual(result.size, (600, 400))
            self.assertEqual(report["items"][0]["trigger"], ["gentle_correction"])
            self.assertEqual(report["items"][0]["rotation_degrees"], 2.0)
            self.assertTrue(report["items"][0]["geometry_crop_applied"])
            self.assertLess(report["items"][0]["geometry_intermediate_size"][0], 600)

    def test_rotation_removes_transformation_borders_and_keeps_aspect(self):
        module = load_module()
        image = Image.new("RGB", (600, 400), "white")
        for x in range(0, 600, 20):
            for y in range(400):
                image.putpixel((x, y), (255, 0, 0))

        result = module._apply_rotation(image, 2.0)

        self.assertLess(result.width, image.width)
        self.assertLess(result.height, image.height)
        self.assertAlmostEqual(result.width / result.height, 1.5, places=2)

    def test_mild_perspective_transform_changes_geometry_without_changing_canvas(self):
        module = load_module()
        image = Image.new("RGB", (300, 200), "white")
        for x in range(0, 300, 15):
            for y in range(200):
                image.putpixel((x, y), (0, 0, 0))
        corners = [[0.02, 0.01], [0.98, 0.02], [0.99, 0.99], [0.01, 0.98]]

        result = module._apply_perspective(image, corners)

        self.assertEqual(result.size, image.size)
        self.assertNotEqual(
            hashlib.sha256(result.tobytes()).hexdigest(),
            hashlib.sha256(image.tobytes()).hexdigest(),
        )

    def test_tiny_inpaint_changes_only_requested_neighborhood(self):
        module = load_module()
        image = Image.new("RGB", (200, 200), "blue")
        for x in range(98, 103):
            for y in range(98, 103):
                image.putpixel((x, y), (255, 0, 0))
        polygons = [[[0.48, 0.48], [0.52, 0.48], [0.52, 0.52], [0.48, 0.52]]]

        result = module.apply_local_inpaint(image, polygons)

        self.assertEqual(result.getpixel((20, 20)), image.getpixel((20, 20)))
        self.assertNotEqual(result.getpixel((100, 100)), image.getpixel((100, 100)))


if __name__ == "__main__":
    unittest.main()
