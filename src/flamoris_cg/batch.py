"""Atomic data-only edits before one Blender build, not arbitrary bpy commands."""
import copy
import hashlib

from .spec import validate_scene
from .data_contract import canonical, fields


def apply_batch(spec, batch):
    fields(batch, ("schema_version", "operations"))
    if type(batch["schema_version"]) is not int or batch["schema_version"] != 1:
        raise ValueError("unsupported batch schema")
    operations = batch["operations"]
    if not isinstance(operations, list) or not 1 <= len(operations) <= 64:
        raise ValueError("batch requires 1..64 operations")
    validate_scene(spec)
    result = copy.deepcopy(spec)
    objects = {obj["id"]: obj for obj in result["objects"]}
    changed = set()
    for op in operations:
        if not isinstance(op, dict):
            raise ValueError("operation must be an object")
        kind = op.get("type")
        if kind in ("set_location", "set_scale", "set_color", "set_keyframes"):
            fields(op, ("type", "object_id", "value"))
            if not isinstance(op["object_id"], str) or op["object_id"] not in objects:
                raise ValueError("unknown object ID")
            objects[op["object_id"]][kind[4:]] = copy.deepcopy(op["value"])
            changed.add(op["object_id"])
        elif kind in ("set_camera", "set_render"):
            fields(op, ("type", "value"))
            result[kind[4:]] = copy.deepcopy(op["value"])
            changed.add(kind[4:])
        else:
            raise ValueError("unsupported batch operation")
        # Reject an invalid intermediate edit rather than silently repairing it
        # with a later operation. Caller input remains unchanged on any failure.
        validate_scene(result)
    return result, {"operations": len(operations), "changed_ids": sorted(changed),
        "before_sha256": hashlib.sha256(canonical(spec).encode()).hexdigest(),
        "after_sha256": hashlib.sha256(canonical(result).encode()).hexdigest()}
