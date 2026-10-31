"""Headless Blender laboratory: create an editable .blend from a bounded JSON spec.

Example:
  blender -b --python-exit-code 1 --python blender/build_scene.py -- \
    --spec examples/hello_motion.json --output outputs/hello --preview

Requires Blender's own bpy; no arbitrary Python from the input JSON is executed.
"""
import argparse
import hashlib
from datetime import datetime, timezone
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from flamoris_cg.spec import load_scene


def parse_args():
    args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    parser = argparse.ArgumentParser(description="FLAMORIS-CG Blender lab")
    parser.add_argument("--spec", required=True, help="Validated scene JSON")
    parser.add_argument("--output", required=True, help="NEW output directory")
    outputs = parser.add_mutually_exclusive_group()
    outputs.add_argument("--preview", action="store_true")
    outputs.add_argument("--sequence", action="store_true")
    return parser.parse_args(args)


def build(spec):
    import bpy
    from mathutils import Vector

    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.frame_start = 1
    scene.frame_end = spec["duration_frames"]
    scene.render.fps = spec["fps"]
    scene.render.resolution_x = spec["render"]["width"]
    scene.render.resolution_y = spec["render"]["height"]
    scene.render.resolution_percentage = 100
    scene.render.engine = "CYCLES"
    scene.cycles.samples = spec["render"]["samples"]
    scene.cycles.device = "CPU"  # No implicit GPU use or host configuration changes
    scene.render.image_settings.file_format = "PNG"

    world = bpy.data.worlds.new("CG_Lab_World")
    scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    if bg:
        bg.inputs["Color"].default_value = (0.025, 0.025, 0.035, 1)
        bg.inputs["Strength"].default_value = 1.0

    for description in spec["objects"]:
        kind = description["primitive"]
        if kind == "cube":
            bpy.ops.mesh.primitive_cube_add()
        elif kind == "uv_sphere":
            bpy.ops.mesh.primitive_uv_sphere_add(segments=24, ring_count=16)
        obj = bpy.context.object
        obj.name = "CG_" + description["id"]
        obj["cg_id"] = description["id"]
        obj.location = description["location"]
        obj.scale = description["scale"]
        material = bpy.data.materials.new("CG_Mat_" + description["id"])
        material.diffuse_color = (*description["color"], 1.0)
        material.use_nodes = True
        principled = material.node_tree.nodes.get("Principled BSDF")
        if principled:
            principled.inputs["Base Color"].default_value = (*description["color"], 1.0)
        obj.data.materials.append(material)
        for key in description.get("keyframes", []):
            obj.location = key["location"]
            obj.keyframe_insert(data_path="location", frame=key["frame"])
        if obj.animation_data and obj.animation_data.action:
            action = obj.animation_data.action
            # Keyed animation is intended as a simple reproducible motion.
            if hasattr(action, "fcurves"):
                for curve in action.fcurves:
                    for point in curve.keyframe_points:
                        point.interpolation = "LINEAR"

    camera_data = bpy.data.cameras.new("CG_Camera")
    camera = bpy.data.objects.new("CG_Camera", camera_data)
    scene.collection.objects.link(camera)
    camera.location = spec["camera"]["location"]
    direction = Vector(spec["camera"]["target"]) - camera.location
    camera.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    scene.camera = camera

    for index, light in enumerate(spec["lights"]):
        data = bpy.data.lights.new(f"CG_Light_{index}", type="POINT")
        data.energy = light["energy"]
        obj = bpy.data.objects.new(data.name, data)
        scene.collection.objects.link(obj)
        obj.location = light["location"]

    scene.frame_set(1)
    return scene


def main():
    import bpy
    args = parse_args()
    spec = load_scene(args.spec)
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    scene = build(spec)
    native = output / "scene.blend"
    bpy.ops.wm.save_as_mainfile(filepath=str(native))
    artifacts = ["scene.blend"]
    if args.preview:
        scene.frame_set(max(1, (spec["duration_frames"] + 1) // 2))
        scene.render.filepath = str(output / "preview.png")
        bpy.ops.render.render(write_still=True)
        artifacts.append("preview.png")
    elif args.sequence:
        sequence = output / "frames"
        sequence.mkdir()
        scene.render.filepath = str(sequence / "frame_")
        bpy.ops.render.render(animation=True)
        artifacts.append("frames/")
    manifest = {
        "format": "flamoris-cg-lab-result",
        "version": 1,
        "blender": bpy.app.version_string,
        "fps": spec["fps"],
        "duration_frames": spec["duration_frames"],
        "render_device": "CPU",
        "artifacts": artifacts,
        "notes": "Keyframed motion; no physics, GPU selection, or encoded video.",
    }
    if args.preview:
        preview = output / "preview.png"
        manifest["preview"] = {
            "frame": scene.frame_current,
            "camera": scene.camera.name,
            "width": scene.render.resolution_x,
            "height": scene.render.resolution_y,
            "byte_length": preview.stat().st_size,
            "sha256": hashlib.sha256(preview.read_bytes()).hexdigest(),
            "spec_sha256": hashlib.sha256(json.dumps(spec, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
        }
    (output / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print("FLAMORIS-CG LAB OK", str(output))


if __name__ == "__main__":
    main()

