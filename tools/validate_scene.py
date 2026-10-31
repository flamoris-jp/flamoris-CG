"""Validate a CG laboratory JSON file without Blender."""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from flamoris_cg.spec import load_scene


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("scene")
    args = parser.parse_args()
    spec = load_scene(args.scene)
    print(f"VALID CG LAB SCENE: {len(spec['objects'])} objects, "
          f"{spec['duration_frames']} frames at {spec['fps']} fps")


if __name__ == "__main__":
    main()
