"""Prepare one completed CG result and register it in a NEW Kachinco test project."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from flamoris_cg.handoff import prepare, import_test


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='operation', required=True)
    prep = sub.add_parser('prepare', help='Offline ZIP -> verified opaque H.264 MP4')
    prep.add_argument('--result', required=True)
    prep.add_argument('--job-id', required=True)
    prep.add_argument('--result-sha256', required=True)
    prep.add_argument('--ffmpeg', default='ffmpeg')
    imp = sub.add_parser('import-test', help='Only a fresh, isolated Kachinco CLI project')
    imp.add_argument('--handoff', required=True, help='Successful prepare handoff.json')
    imp.add_argument('--kachinco', required=True, help='Installed trusted CLI executable')
    for p in (prep, imp):
        p.add_argument('--output', required=True, help='NEW directory under an existing parent')
        p.add_argument('--ffprobe', default='ffprobe')
    args = parser.parse_args()
    try:
        if args.operation == 'prepare':
            result = prepare(args.result, args.job_id, args.result_sha256, args.output, args.ffmpeg, args.ffprobe)
        else:
            result = import_test(args.handoff, args.output, args.kachinco, args.ffprobe)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except Exception as exc:
        print(json.dumps({'success': False, 'error': type(exc).__name__, 'message': str(exc)}), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
