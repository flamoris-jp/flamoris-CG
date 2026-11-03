"""Short-lived CLI for durable render jobs; never waits for a render to finish."""
import argparse
import json
from pathlib import Path
import shutil
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/"src"))
from flamoris_cg.render_jobs import JobConfig, RenderJobs, fields
from flamoris_cg.spec import _no_duplicate_pairs, _no_constant


def read_json(path):
    raw = Path(path).read_bytes()
    if len(raw) > 256 * 1024:
        raise ValueError("input byte limit")
    return json.loads(raw.decode("utf-8"), object_pairs_hook=_no_duplicate_pairs, parse_constant=_no_constant)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True, help='Trusted operator configuration; never request-supplied')
    sub = parser.add_subparsers(dest='operation', required=True)
    register = sub.add_parser('register', help='Trusted local native-scene registration')
    register.add_argument('scene_id')
    register.add_argument('--blend', required=True)
    register.add_argument('--metadata', required=True)
    submit = sub.add_parser('submit')
    submit.add_argument('--request', required=True)
    for name in ['status', 'cancel', 'result', 'prune']:
        p = sub.add_parser(name)
        p.add_argument('job_id')
        if name == 'result':
            p.add_argument('--export', help='NEW local ZIP path for one bulk transfer')
    listing = sub.add_parser('list')
    listing.add_argument('--limit', type=int, default=20)
    args = parser.parse_args()
    config = read_json(args.config)
    required = ('state_root', 'shared_root', 'manager_url')
    fields(config, required, ('max_active', 'max_jobs', 'max_output_bytes', 'max_storage_bytes',
                             'poll_seconds', 'timeout_seconds', 'worker_tag', 'retention_seconds'))
    service = RenderJobs(JobConfig(**config))
    if args.operation == 'register':
        result = service.register_scene(args.scene_id, args.blend, read_json(args.metadata))
    elif args.operation == 'submit':
        result = service.submit(read_json(args.request))
    elif args.operation == 'list':
        result = service.list_jobs(args.limit)
    else:
        result = getattr(service, args.operation)(args.job_id)
        if args.operation == 'result' and args.export:
            if not result['ready']:
                raise ValueError('result is not ready')
            destination = Path(args.export)
            # Exclusive create; never overwrite caller files.
            with destination.open('xb') as out, service.artifact_path(args.job_id).open('rb') as src:
                shutil.copyfileobj(src, out)
    print(json.dumps(result, ensure_ascii=False, allow_nan=False))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(json.dumps({'error': type(exc).__name__, 'message': str(exc)}), file=sys.stderr)
        raise SystemExit(2)
