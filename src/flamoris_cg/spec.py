"""Strict, bounded input specification for the early Blender laboratory.

Not the long-term FLAMORIS-CG language and not a Cinema Scene/Take document.
"""
import json
import math
import re
from pathlib import Path

MAX_JSON_BYTES = 256 * 1024
IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]{0,63}$")


def _object(value, required, optional=(), label="object"):
    if not isinstance(value, dict):
        raise ValueError(f"{label}: expected object")
    unknown = set(value) - set(required) - set(optional)
    missing = set(required) - set(value)
    if unknown or missing:
        raise ValueError(f"{label}: missing {sorted(missing)} / unsupported {sorted(unknown)}")


def _int(value, lo, hi, label):
    if type(value) is not int or not lo <= value <= hi:
        raise ValueError(f"{label}: expected integer {lo}..{hi}")


def _number(value, lo, hi, label):
    if type(value) not in (float, int) or not math.isfinite(value) or not lo <= value <= hi:
        raise ValueError(f"{label}: expected finite number {lo}..{hi}")


def _vec(value, lo, hi, label):
    if not isinstance(value, list) or len(value) != 3:
        raise ValueError(f"{label}: expected three-element array")
    for component in value:
        _number(component, lo, hi, label)


def _id(value):
    if not isinstance(value, str) or not IDENTIFIER.fullmatch(value):
        raise ValueError("object.id: invalid identifier")


def validate_scene(spec):
    """Validate a trial CG description. Return it unchanged on success."""
    _object(spec, ("schema_version", "fps", "duration_frames", "render",
                   "camera", "lights", "objects"), label="scene")
    if type(spec["schema_version"]) is not int or spec["schema_version"] != 1:
        raise ValueError("unsupported schema_version")
    _int(spec["fps"], 1, 120, "fps")
    _int(spec["duration_frames"], 1, 240, "duration_frames")

    render = spec["render"]
    _object(render, ("width", "height", "samples"), label="render")
    _int(render["width"], 64, 1920, "render.width")
    _int(render["height"], 64, 1080, "render.height")
    _int(render["samples"], 1, 64, "render.samples")

    cam = spec["camera"]
    _object(cam, ("location", "target"), label="camera")
    _vec(cam["location"], -1000, 1000, "camera.location")
    _vec(cam["target"], -1000, 1000, "camera.target")
    if sum((a - b) ** 2 for a, b in zip(cam["location"], cam["target"])) < 1e-10:
        raise ValueError("camera location and target must differ")

    lights = spec["lights"]
    if not isinstance(lights, list) or not 1 <= len(lights) <= 8:
        raise ValueError("lights: expected 1..8 items")
    for light in lights:
        _object(light, ("location", "energy"), label="light")
        _vec(light["location"], -1000, 1000, "light.location")
        _number(light["energy"], 0, 100000, "light.energy")

    objects = spec["objects"]
    if not isinstance(objects, list) or not 1 <= len(objects) <= 32:
        raise ValueError("objects: expected 1..32 items")
    used = set()
    for obj in objects:
        _object(obj, ("id", "primitive", "location", "scale", "color"),
                ("keyframes",), "object")
        _id(obj["id"])
        if obj["id"] in used:
            raise ValueError("objects: duplicate id")
        used.add(obj["id"])
        if obj["primitive"] not in ("cube", "uv_sphere"):
            raise ValueError("object.primitive: unsupported kind")
        _vec(obj["location"], -1000, 1000, "object.location")
        _vec(obj["scale"], 0.0001, 100, "object.scale")
        _vec(obj["color"], 0, 1, "object.color")
        frames = obj.get("keyframes", [])
        if not isinstance(frames, list) or len(frames) > 240:
            raise ValueError("keyframes: expected bounded list")
        previous = 0
        for kf in frames:
            _object(kf, ("frame", "location"), label="keyframe")
            _int(kf["frame"], 1, spec["duration_frames"], "keyframe.frame")
            if kf["frame"] <= previous:
                raise ValueError("keyframes: frames must strictly increase")
            previous = kf["frame"]
            _vec(kf["location"], -1000, 1000, "keyframe.location")
    return spec


def _no_duplicate_pairs(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise ValueError(f"duplicate JSON property: {key}")
        out[key] = value
    return out


def _no_constant(value):
    raise ValueError(f"non-finite JSON constant: {value}")


def load_scene(path):
    raw = Path(path).read_bytes()
    if len(raw) > MAX_JSON_BYTES:
        raise ValueError("JSON file too large")
    scene = json.loads(raw.decode("utf-8"), object_pairs_hook=_no_duplicate_pairs,
                       parse_constant=_no_constant)
    return validate_scene(scene)
