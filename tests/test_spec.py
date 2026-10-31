"""Portable tests for the laboratory scene spec. Blender is not required."""
import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from flamoris_cg.spec import load_scene, validate_scene


class SceneSpecTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scene = load_scene(ROOT / "examples" / "hello_motion.json")

    def test_example_is_valid(self):
        self.assertEqual(validate_scene(copy.deepcopy(self.scene))["fps"], 24)

    def test_unknown_field_rejected(self):
        scene = copy.deepcopy(self.scene)
        scene["arbitrary_blender_python"] = "print('bad')"
        with self.assertRaises(ValueError):
            validate_scene(scene)

    def test_duplicate_object_ids_rejected(self):
        scene = copy.deepcopy(self.scene)
        scene["objects"][1]["id"] = scene["objects"][0]["id"]
        with self.assertRaises(ValueError):
            validate_scene(scene)

    def test_bad_keyframe_order_rejected(self):
        scene = copy.deepcopy(self.scene)
        scene["objects"][1]["keyframes"][1]["frame"] = 1
        with self.assertRaises(ValueError):
            validate_scene(scene)

    def test_boolean_numeric_rejected(self):
        scene = copy.deepcopy(self.scene)
        scene["fps"] = True
        with self.assertRaises(ValueError):
            validate_scene(scene)

    def test_non_finite_rejected(self):
        scene = copy.deepcopy(self.scene)
        scene["objects"][0]["location"][0] = float("nan")
        with self.assertRaises(ValueError):
            validate_scene(scene)

    def test_duplicate_json_property_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.json"
            path.write_text('{"fps":24,"fps":30}', encoding="utf-8")
            with self.assertRaises(ValueError):
                load_scene(path)

    def test_oversized_scene_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "large.json"
            path.write_text(" " * (256 * 1024 + 1), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_scene(path)


if __name__ == "__main__":
    unittest.main()
