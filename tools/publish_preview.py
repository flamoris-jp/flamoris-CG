"""Publish an on-demand CG preview bundle from trusted, pinned source checkouts."""
import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--capture-root', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--rid', choices=['linux-x64', 'win-x64'], required=True)
    p.add_argument('--dotnet', default='dotnet')
    args = p.parse_args()
    repo = Path(__file__).resolve().parents[1]
    capture = args.capture_root.resolve(strict=True)
    dependency = json.loads((repo / 'config/preview-dependencies.json').read_text())
    actual = subprocess.check_output(['git', '-C', str(capture), 'rev-parse', 'HEAD'], text=True).strip()
    if actual != dependency['capture_commit']:
        raise SystemExit('Capture checkout must match preview-dependencies.json')
    # Source checkouts must be reviewed and clean. git diff is read-only.
    if subprocess.check_output(['git', '-C', str(capture), 'status', '--porcelain'], text=True).strip():
        raise SystemExit('Capture checkout must be clean')
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    for name, project in [('preview', repo / 'mcp/Flamoris.Cg.Preview'),
                          ('imaging', capture / 'src/Flamoris.Capture.Imaging.Cli')]:
        subprocess.run([args.dotnet, 'publish', str(project), '-c', 'Release', '-r', args.rid,
                        '--self-contained', 'true', '-o', str(output / name),
                        '-p:CaptureSourceRoot=' + str(capture)], check=True)
        # Retain package/runtime license material alongside the self-contained binaries.
        assets = json.loads((project / 'obj/project.assets.json').read_text())
        notices = output / name / 'licenses'
        notices.mkdir(exist_ok=True)
        for identity, library in assets['libraries'].items():
            if library.get('type') != 'package':
                continue
            for folder in assets['packageFolders']:
                package = Path(folder) / library['path']
                if not package.is_dir():
                    continue
                for source in package.iterdir():
                    if source.is_file() and any(word in source.name.lower() for word in ['license', 'notice']):
                        shutil.copy2(source, notices / (identity.replace('/', '-') + '-' + source.name))
                break
    for directory in ['blender', 'src/flamoris_cg', 'examples', 'config']:
        shutil.copytree(repo / directory, output / directory, ignore=shutil.ignore_patterns('__pycache__'))
    shutil.copy2(repo / 'tools/preview_client.py', output / 'preview_client.py')
    shutil.copy2(repo / 'LICENSE', output / 'LICENSE')
    shutil.copy2(repo / 'docs/preview-mcp.md', output / 'README.md')
    receipt = dict(format='flamoris-cg-preview-bundle', version=1, rid=args.rid, dependencies=dependency,
                   files={str(f.relative_to(output)): hashlib.sha256(f.read_bytes()).hexdigest()
                          for f in output.rglob('*') if f.is_file()})
    (output / 'bundle.json').write_text(json.dumps(receipt, indent=2) + '\n')


if __name__ == '__main__':
    main()
