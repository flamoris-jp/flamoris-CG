"""Official MCP-client smoke test with a synthetic, immutable managed clip."""
import argparse
import asyncio
import base64
import hashlib
import json
import struct
import tempfile
import zlib
from pathlib import Path
from preview_client import fetch


def png():
    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data))
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', 2, 1, 8, 6, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(b'\x00\xff\x00\x00\xff\x00\x00\xff\x80')) + chunk(b'IEND', b''))


async def run(executable):
    with tempfile.TemporaryDirectory(prefix='cg-mcp-') as temporary:
        root = Path(temporary)
        clip = root / 'synthetic'
        clip.mkdir()
        data = png()
        (clip / 'preview.png').write_bytes(data)
        manifest = dict(format='flamoris-cg-lab-result', version=1, blender='synthetic', duration_frames=24,
                        render_device='CPU', artifacts=['preview.png'], preview=dict(
                            frame=12, camera='CG_Camera', width=2, height=1, byte_length=len(data),
                            sha256=hashlib.sha256(data).hexdigest(), spec_sha256='a' * 64,
                            created_at_utc='2026-11-01T00:00:00+00:00'))
        (clip / 'manifest.json').write_text(json.dumps(manifest))
        for fmt in ['png', 'jpeg']:
            result = await fetch(executable, root, 'synthetic', image_format=fmt)
            assert not result.get('isError'), result
            images = [c for c in result['content'] if c['type'] == 'image']
            assert len(images) == 1
            meta = result['structuredContent']['image']
            image = base64.b64decode(images[0]['data'], validate=True)
            assert images[0]['mimeType'] == meta['mimeType']
            assert len(image) == meta['byteLength'] <= 1048576
            assert hashlib.sha256(image).hexdigest() == meta['sha256']
            assert 'data' not in meta and 'data' not in result['structuredContent']['provenance']
        for clip_id in ['absent', '../synthetic']:
            result = await fetch(executable, root, clip_id)
            assert result['isError'] and not any(c['type'] == 'image' for c in result['content'])
        print('Official MCP stdio: PNG/JPEG bytes, metadata, missing/traversal errors passed')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--executable', required=True)
    asyncio.run(run(parser.parse_args().executable))
