"""Geometry-contract regressions using the saved real-photo analysis results.

These checks exercise edits to real scene descriptions without running ONNX or
pretending to validate photographic fidelity. The end-to-end evidence lives in
validation/ and is produced separately by the worker/browser pipeline.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
from pathlib import Path
import unittest

import numpy as np
from PIL import Image

from backend.reconstruction import ReconstructionError, apply_corrections
from backend.scene_schema import validate_scene

ROOT = Path(__file__).resolve().parents[1]


def load_scene(name: str) -> dict:
    return json.loads((ROOT / "validation" / name / "scene.json").read_text())


def wall_distance(obj: dict, wall: dict) -> float:
    """Signed horizontal distance from a box centre to its wall's inner plane."""
    dx = wall["end"][0] - wall["start"][0]
    dz = wall["end"][1] - wall["start"][1]
    length = math.hypot(dx, dz)
    px = obj["position"][0] - wall["start"][0]
    pz = obj["position"][2] - wall["start"][1]
    return (-dz * px + dx * pz) / length


class ActualPhotoSceneContract(unittest.TestCase):
    def test_both_photo_results_validate_and_reference_the_corresponding_photo(self):
        for name in ("warehouse", "room"):
            with self.subTest(photo=name):
                scene = load_scene(name)
                self.assertEqual(validate_scene(scene), scene)
                source = ROOT / "validation" / "photos" / f"{name}.jpg"
                self.assertEqual(scene["source"]["sha256"], hashlib.sha256(source.read_bytes()).hexdigest())
                self.assertGreater(scene["analysis"]["diagnostics"]["floor_coverage"], .095)
                self.assertTrue(scene["analysis"]["warnings"])
                for material in scene["materials"].values():
                    if material["texture"]:
                        self.assertTrue((ROOT / "validation" / name / material["texture"]).is_file())

    def test_different_photos_have_distinct_structured_geometry_and_materials(self):
        warehouse, room = load_scene("warehouse"), load_scene("room")
        self.assertNotEqual(warehouse["room"]["floor_polygon"], room["room"]["floor_polygon"])
        self.assertNotEqual(warehouse["materials"]["floor"]["color"], room["materials"]["floor"]["color"])
        self.assertGreater(len(warehouse["objects"]), 0)
        doors = [opening for wall in room["room"]["walls"] for opening in wall["openings"] if opening["kind"] == "door"]
        self.assertGreaterEqual(len(doors), 1)
        self.assertTrue(all(door["bottom"] == 0 for door in doors))

    def test_material_paths_and_references_are_validated(self):
        scene = load_scene("warehouse")
        scene["materials"]["floor"]["texture"] = "../private.png"
        with self.assertRaises(ValueError):
            validate_scene(scene)
        scene = load_scene("room")
        scene["room"]["walls"][0]["material"] = "missing-finish"
        with self.assertRaises(ValueError):
            validate_scene(scene)

    def test_estimated_front_wall_closes_the_room_behind_the_source_camera(self):
        for name in ("warehouse", "room"):
            with self.subTest(photo=name):
                scene = load_scene(name)
                room = scene["room"]
                front = next(wall for wall in room["walls"] if wall["id"] == "front-estimated")
                self.assertEqual(front["start"], [room["width"] / 2, room["depth"] / 2])
                self.assertEqual(front["end"], [-room["width"] / 2, room["depth"] / 2])
                self.assertGreater(front["start"][1], scene["camera"]["position"][2])
                self.assertEqual(front["openings"], [])
                material = scene["materials"][front["material"]]
                self.assertIsNone(material["texture"])
                self.assertEqual(material["color"], scene["materials"]["wall"]["color"])
                self.assertTrue(any("behind the source camera" in warning for warning in scene["analysis"]["warnings"]))

    def test_rectified_floor_textures_repeat_without_image_edge_seams(self):
        for name in ("warehouse", "room"):
            with self.subTest(photo=name):
                scene = load_scene(name)
                texture = ROOT / "validation" / name / scene["materials"]["floor"]["texture"]
                pixels = np.asarray(Image.open(texture))
                np.testing.assert_array_equal(pixels[:, 0], pixels[:, -1])
                np.testing.assert_array_equal(pixels[0], pixels[-1])
                self.assertGreater(float(pixels.std()), .5)
class Corrections(unittest.TestCase):
    def test_room_scale_keeps_cameras_openings_and_object_wall_anchors_consistent(self):
        ratios = (1.5, 1.2, .8)  # x, y, z
        for name in ("warehouse", "room"):
            with self.subTest(photo=name):
                scene = load_scene(name)
                room = scene["room"]
                corrected = apply_corrections(scene, {"room": {
                    "width": room["width"] * ratios[0],
                    "height": room["height"] * ratios[1],
                    "depth": room["depth"] * ratios[2],
                }})
                for key in ("camera", "walk_start"):
                    for prop in ("position", "target"):
                        for i, value in enumerate(scene[key][prop]):
                            self.assertAlmostEqual(corrected[key][prop][i], value * ratios[i])
                for old_wall, new_wall in zip(room["walls"], corrected["room"]["walls"]):
                    old_length = math.dist(old_wall["start"], old_wall["end"])
                    new_length = math.dist(new_wall["start"], new_wall["end"])
                    for old_opening, new_opening in zip(old_wall["openings"], new_wall["openings"]):
                        self.assertAlmostEqual(new_opening["offset"] / new_length, old_opening["offset"] / old_length)
                        self.assertAlmostEqual(new_opening["width"] / new_length, old_opening["width"] / old_length)
                        self.assertAlmostEqual(new_opening["height"], old_opening["height"] * ratios[1])
                        self.assertAlmostEqual(new_opening["bottom"], old_opening["bottom"] * ratios[1])
                by_id = {wall["id"]: wall for wall in corrected["room"]["walls"]}
                for old_obj, new_obj in zip(scene["objects"], corrected["objects"]):
                    self.assertEqual(new_obj["wall_id"], old_obj["wall_id"])
                    for i, value in enumerate(old_obj["position"]):
                        self.assertAlmostEqual(new_obj["position"][i], value * ratios[i])
                    self.assertGreater(wall_distance(new_obj, by_id[new_obj["wall_id"]]), 0)

    def test_side_wall_object_local_width_tracks_room_depth_when_room_is_resized(self):
        scene = load_scene("warehouse")
        obj = scene["objects"][0]
        # Exercise the same real detected enclosure at a different supported
        # wall orientation; this isolates local-vs-world dimension scaling.
        obj["wall_id"] = "left"
        obj["rotation_y"] = math.pi / 2
        obj["position"] = [-scene["room"]["width"] / 2 + .4, 1, 0]
        old_dimensions = list(obj["dimensions"])
        corrected = apply_corrections(scene, {"room": {
            "width": scene["room"]["width"] * 1.5,
            "depth": scene["room"]["depth"] * .8,
        }})
        edited = corrected["objects"][0]
        self.assertAlmostEqual(edited["dimensions"][0], old_dimensions[0] * .8)
        self.assertAlmostEqual(edited["dimensions"][2], old_dimensions[2] * 1.5)
        self.assertAlmostEqual(edited["rotation_y"], math.pi / 2)

    def test_skewed_wall_keeps_attached_object_offset_and_orientation(self):
        scene = load_scene("warehouse")
        obj = scene["objects"][0]
        old_wall = next(w for w in scene["room"]["walls"] if w["id"] == obj["wall_id"])
        original_distance = wall_distance(obj, old_wall)
        corners = copy.deepcopy(scene["room"]["floor_polygon"])
        corners[0][1] -= .5
        corners[1][1] += .3
        corrected = apply_corrections(scene, {"wall_corners": corners})
        wall = next(w for w in corrected["room"]["walls"] if w["id"] == obj["wall_id"])
        edited = corrected["objects"][0]
        self.assertAlmostEqual(wall_distance(edited, wall), original_distance)
        self.assertAlmostEqual(edited["rotation_y"], -math.atan2(wall["end"][1] - wall["start"][1], wall["end"][0] - wall["start"][0]))
        self.assertEqual(corrected["room"]["floor_polygon"], corners)

    def test_source_camera_alignment_does_not_move_the_independent_walking_camera(self):
        scene = load_scene("room")
        corrected = apply_corrections(scene, {"camera": {"fov": 62, "pitch": -8}})
        self.assertEqual(corrected["walk_start"], scene["walk_start"])
        self.assertEqual(corrected["camera"]["position"], scene["camera"]["position"])
        self.assertEqual(corrected["camera"]["fov"], 62)
        position, target = corrected["camera"]["position"], corrected["camera"]["target"]
        dy = target[1] - position[1]
        horizontal = math.hypot(target[0] - position[0], target[2] - position[2])
        self.assertAlmostEqual(math.degrees(math.atan2(dy, horizontal)), -8)

    def test_object_edits_preserve_photo_materials_and_do_not_mutate_the_original(self):
        scene = load_scene("warehouse")
        original = copy.deepcopy(scene)
        object_id = scene["objects"][0]["id"]
        corrected = apply_corrections(scene, {"objects": [{"id": object_id, "position": [0, 1, 0], "dimensions": [1, 2, .5]}]})
        self.assertEqual(corrected["objects"][0]["position"], [0, 1, 0])
        self.assertEqual(corrected["objects"][0]["dimensions"], [1, 2, .5])
        self.assertEqual(corrected["materials"], original["materials"])
        self.assertEqual(corrected["source"], original["source"])
        self.assertEqual(scene, original)

    def test_invalid_polygons_nonfinite_values_and_unknown_edits_are_rejected(self):
        scene = load_scene("warehouse")
        invalid = [
            {"room": {"width": 0}},
            {"room": {"height": float("nan")}},
            {"camera": {"pitch": 100}},
            {"camera": {"target": [0, float("inf"), 0]}},
            {"objects": [{"id": "missing", "position": [0, 0, 0]}]},
            {"objects": [{"id": scene["objects"][0]["id"], "dimensions": [1, -2, 1]}]},
            {"wall_corners": [[0, 0], [1, 1], [0, 1], [1, 0]]},
            {"wall_corners": [[0, 0], [1, 0], [float("nan"), 1], [0, 1]]},
            {"wall_corners": [[0, 0], [1, 0], [1, 1]]},
            {"unknown": 1},
        ]
        for edit in invalid:
            with self.subTest(edit=edit):
                with self.assertRaises((ReconstructionError, ValueError)):
                    apply_corrections(scene, edit)


if __name__ == "__main__":
    unittest.main()
