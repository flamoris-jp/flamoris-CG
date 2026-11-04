"""Contract tests plus real FFmpeg tests; no Blender or live Kachinco acceptance."""
import copy
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import shutil
import stat
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4
import warnings
import zipfile
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from flamoris_cg import handoff as h


def png(width=8, height=8, alpha=255):
    def chunk(tag, data):
        return struct.pack('>I', len(data)) + tag + data + struct.pack('>I', zlib.crc32(tag + data))
    header = struct.pack('>IIBBBBB', width, height, 8, 6, 0, 0, 0)
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', header)
            + chunk(b'IDAT', zlib.compress((b'\0' + bytes([220, 80, 40, alpha]) * width) * height))
            + chunk(b'IEND', b''))


class Fixture(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.job = {'job_id': str(uuid4()), 'status': 'succeeded', 'cancel_requested': False,
                    'scene': {'width': 8, 'height': 8, 'fps': 12, 'frame_start': 1, 'frame_end': 240},
                    'request': {'frames': list(range(1, 181))}}

    def bundle(self, job=None, entries=None):
        job = job or self.job
        path = self.root / (str(uuid4()) + '.zip')
        if entries is None:
            entries = [('job.json', json.dumps(job).encode()), ('diagnostics.json', b'{}')]
            entries += [(f'frames/{f:06d}.png', png()) for f in job['request']['frames']]
        with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as archive:
            with warnings.catch_warnings():
                warnings.simplefilter('ignore', UserWarning)
                for name, data in entries:
                    archive.writestr(name, data)
        return path

    def prepare(self, source=None, output=None):
        source = source or self.bundle()
        return h.prepare(source, self.job['job_id'], h.digest(source), output or self.root / 'prepared')


class HandoffTests(Fixture):
    def setUp(self):
        super().setUp()
        # Contract failures must be portable even when FFmpeg is absent.
        resolver = patch.object(h, 'executable', side_effect=str)
        resolver.start()
        self.addCleanup(resolver.stop)

    def test_bad_result_hash_or_wrong_job_never_runs_commands_or_creates_output(self):
        source = self.bundle()
        for identity, sha in [(self.job['job_id'], '0' * 64), (str(uuid4()), h.digest(source))]:
            with patch.object(h, 'run') as run, self.assertRaises(ValueError):
                h.prepare(source, identity, sha, self.root / 'bad')
            run.assert_not_called()
            self.assertFalse((self.root / 'bad').exists())

    def test_non_success_and_purged_results_refused(self):
        for fields in ({'status': 'running'}, {'status': 'failed'}, {'status': 'canceled'},
                       {'purged': True}, {'cancel_requested': True}):
            with self.subTest(fields=fields), patch.object(h, 'run') as run:
                source = self.bundle({**self.job, **fields})
                with self.assertRaises(ValueError):
                    self.prepare(source)
                run.assert_not_called()

    def test_sparse_unordered_duplicate_noninteger_frames_and_odd_dimensions_refused(self):
        for frames in ([1, 3], [2, 1], [1, 1], [True], [], [1.0], list(range(1, 242))):
            with self.subTest(frames=frames), self.assertRaises(ValueError):
                h.timing(self.job['scene'], frames)
        for scene in ({'width': 7}, {'height': 1082}, {'fps': True}, {'fps': float('nan')},
                      {'fps': 0}, {'fps': 24000/1001}, {'frame_end': 2}):
            with self.subTest(scene=scene), self.assertRaises(ValueError):
                h.timing({**self.job['scene'], **scene}, [1, 2, 3])

    def test_exact_decimal_rate_and_duration_ticks(self):
        fps, duration = h.timing({**self.job['scene'], 'fps': 23.976}, [1, 2, 3])
        self.assertEqual(fps, Fraction(2997, 125))
        self.assertEqual(duration, Fraction(125, 999))

    def test_cli_stdout_json_is_separate_from_success_diagnostics(self):
        output, errors = self.root / 'out.json', self.root / 'diagnostics.txt'
        h.run([sys.executable, '-c',
               'import sys; print("{\\"success\\":true}"); print("diagnostic", file=sys.stderr)'],
              output, error_log=errors)
        self.assertTrue(h.read_json(output)['success'])
        self.assertEqual(errors.read_text().strip(), 'diagnostic')

    def test_zip_missing_extra_duplicate_traversal_or_symlink_refused(self):
        base = [('job.json', json.dumps(self.job).encode()), ('diagnostics.json', b'{}')]
        frames = [(f'frames/{f:06d}.png', png()) for f in self.job['request']['frames']]
        link = zipfile.ZipInfo('frames/000001.png')
        link.create_system = 3
        link.external_attr = (stat.S_IFLNK | 0o777) << 16
        for entries in (base + frames[:-1], base + frames + [('../escape', b'x')],
                        base + frames + [('job.json', b'{}')],
                        base + [(link, b'/etc/passwd')] + frames[1:]):
            with self.subTest(), patch.object(h, 'run') as run, self.assertRaises(ValueError):
                self.prepare(self.bundle(entries=entries))
            run.assert_not_called()
        self.assertFalse((self.root / 'escape').exists())

    def test_existing_output_and_symlink_parent_refused(self):
        output = self.root / 'existing'
        output.mkdir()
        sentinel = output / 'existing-media-and-history'
        sentinel.write_bytes(b'keep everything')
        with patch.object(h, 'run') as run, self.assertRaises(FileExistsError):
            self.prepare(output=output)
        run.assert_not_called()
        self.assertEqual(sentinel.read_bytes(), b'keep everything')
        if sys.platform != 'win32':
            link = self.root / 'link'
            link.symlink_to(output, target_is_directory=True)
            with self.assertRaises(ValueError):
                self.prepare(output=link / 'new')

    def test_header_mismatch_leaves_failure_receipt_and_no_import(self):
        self.job['request']['frames'] = [1]
        source = self.bundle(entries=[('job.json', json.dumps(self.job).encode()),
            ('diagnostics.json', b'{}'), ('frames/000001.png', png(width=6))])
        with patch.object(h, 'run') as run, self.assertRaisesRegex(ValueError, 'PNG'):
            self.prepare(source)
        run.assert_not_called()
        self.assertFalse(h.read_json(self.root / 'prepared/handoff.json')['success'])

    def test_expanded_zip_budget_refused_before_creating_output(self):
        source = self.bundle(entries=[('job.json', json.dumps(self.job).encode() + b' ' * 6000),
                                     ('diagnostics.json', b' ' * 8000)])
        with patch.object(h, 'MAX_BYTES', 10_000), self.assertRaisesRegex(ValueError, 'expanded'):
            self.prepare(source)
        self.assertFalse((self.root / 'prepared').exists())

    def test_video_metadata_checks_reject_count_rate_duration_codec_and_audio(self):
        video = self.root / 'clip.mp4'
        video.write_bytes(b'fixture')
        stream = {'codec_type': 'video', 'codec_name': 'h264', 'pix_fmt': 'yuv420p',
                  'width': 8, 'height': 8, 'nb_read_frames': '180', 'nb_frames': '180',
                  'avg_frame_rate': '12/1', 'r_frame_rate': '12/1',
                  'duration_ts': 180, 'time_base': '1/12'}
        variants = [{'nb_read_frames': '179'}, {'nb_frames': '181'}, {'width': 10},
                    {'avg_frame_rate': '24/1'}, {'r_frame_rate': '24/1'},
                    {'duration_ts': 179}, {'codec_name': 'hevc'}, {'pix_fmt': 'yuva420p'}]
        for i, fields in enumerate(variants + [{}, {}]):
            report = {'streams': [{**stream, **fields}], 'format': {'duration': '15'}}
            if i == len(variants):
                report['format']['duration'] = '15.01'
            elif i == len(variants) + 1:
                report['streams'].append({'codec_type': 'audio'})
            def probe(command, log, **kwargs):
                h.write_json(log, report)
            with self.subTest(fields=fields), patch.object(h, 'run', side_effect=probe), self.assertRaises(ValueError):
                h.verify_video(video, self.job['scene'], self.job['request']['frames'],
                               'probe', self.root / f'probe-{i}.json')


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'real FFmpeg/ffprobe required')
class FfmpegHandoffTests(Fixture):
    # Contract tests above also run on machines without FFmpeg. These tests use
    # actual codec processes; the CLI boundary below is deliberately simulated.
    def test_real_180_frame_encode_is_15_seconds_and_original_zip_unchanged(self):
        source = self.bundle()
        before = h.digest(source)
        receipt = self.prepare(source)
        self.assertTrue(receipt['success'])
        self.assertEqual(receipt['duration_seconds'], {'numerator': '15', 'denominator': '1'})
        self.assertEqual(receipt['duration_ticks_exact'], {'numerator': '529200000', 'denominator': '1'})
        self.assertEqual(len(receipt['frame_sha256']), 180)
        self.assertEqual(h.digest(source), before)
        self.assertEqual(receipt['mp4_sha256'], h.digest(self.root / 'prepared/clip.mp4'))
        report = h.read_json(self.root / 'prepared/ffprobe.json')
        self.assertEqual(report['streams'][0]['nb_read_frames'], '180')

    def test_real_fractional_rate_non_one_start_and_transparency(self):
        self.job['scene'].update(fps=23.976, frame_start=78)
        self.job['request']['frames'] = [78, 79, 80]
        entries = [('job.json', json.dumps(self.job).encode()), ('diagnostics.json', b'{}')]
        entries += [(f'frames/{f:06d}.png', png(alpha=0)) for f in [78, 79, 80]]
        self.prepare(self.bundle(entries=entries))
        pixels = self.root / 'pixel.rgb'
        h.run(['ffmpeg', '-v', 'error', '-i', str(self.root / 'prepared/clip.mp4'),
               '-frames:v', '1', '-f', 'rawvideo', '-pix_fmt', 'rgb24', str(pixels)], self.root / 'decode.log')
        self.assertLessEqual(max(pixels.read_bytes()), 3)  # Transparent red becomes black.

    def test_real_single_frame_completed_job(self):
        self.job['request']['frames'] = [1]
        receipt = self.prepare()
        self.assertEqual(receipt['duration_seconds'], {'numerator': '1', 'denominator': '12'})
        self.assertTrue(receipt['success'])

    def test_corrupt_png_body_and_command_failure_have_no_success_receipt(self):
        self.job['request']['frames'] = [1]
        source = self.bundle(entries=[('job.json', json.dumps(self.job).encode()),
            ('diagnostics.json', b'{}'), ('frames/000001.png', png()[:24])])
        with self.assertRaises(ValueError):
            self.prepare(source)
        self.assertFalse(h.read_json(self.root / 'prepared/handoff.json')['success'])

    def cli_boundary(self, corrupt=False):
        """Simulate observed CLI JSON/argv contract, not Kachinco acceptance."""
        real_run = h.run
        calls = []
        state = {}

        def invoke(command, log, **kwargs):
            if command[0] != 'TEST-KACHINCO':
                return real_run(command, log, **kwargs)
            calls.append(command)
            args = command[1:]
            if args[:2] == ['project', 'new']:
                self.assertEqual(args[args.index('--width') + 1], '1920')
                self.assertEqual(args[args.index('--height') + 1], '1080')
                project = {'id': str(uuid4()), 'name': 'CG handoff TEST', 'assets': [],
                           'sequences': [{'id': str(uuid4()), 'tracks': [], 'handEdit': 'preserve'}]}
                envelope = {'project': project, 'authoring': [{'clappers': []}], 'generatedAssets': []}
                seed = Path(args[args.index('--output') + 1])
                h.write_json(seed, envelope)
                state[str(seed)] = {'revision': '1', 'project': envelope, 'media': []}
                h.write_json(log, {'projectId': project['id']})
            elif args[:2] == ['media', 'import']:
                seed = args[2]
                video = args[args.index('--source') + 1]
                imported = args[args.index('--output') + 1]
                after = copy.deepcopy(state[seed])
                after['revision'] = '2'
                after['project']['project']['assets'] = [{'id': str(uuid4()), 'kind': 'Mov',
                    'durationTicks': str(15 * h.TICKS)}]
                after['media'] = [{'isAvailable': True, 'resolvedPath': video}]
                if corrupt:
                    after['project']['project']['sequences'][0]['handEdit'] = 'destroyed'
                state[imported] = after
                h.write_json(imported, after['project'])
                h.write_json(log, {'success': True})
            elif args[:2] == ['project', 'info']:
                h.write_json(log, state[args[2]])
            elif args[:2] == ['project', 'validate']:
                h.write_json(log, {'valid': True})
            else:
                self.fail('unexpected CLI mutation: ' + repr(command))
        return invoke, calls

    def test_import_contract_uses_only_new_seed_and_preserves_unrelated_state(self):
        self.prepare()
        sentinel = self.root / 'production.fkproj'
        sentinel.write_bytes(b'existing media and undo history')
        invoke, calls = self.cli_boundary()
        real_executable = h.executable
        with patch.object(h, 'run', side_effect=invoke), patch.object(h, 'executable',
                side_effect=lambda p: 'TEST-KACHINCO' if p == 'test-cli' else real_executable(p)):
            receipt = h.import_test(self.root / 'prepared/handoff.json', self.root / 'test-project', 'test-cli')
        self.assertTrue(receipt['success'])
        self.assertEqual(sentinel.read_bytes(), b'existing media and undo history')
        self.assertEqual([c[1:3] for c in calls], [['project', 'new'], ['project', 'info'],
                         ['media', 'import'], ['project', 'validate'], ['project', 'info']])
        self.assertEqual(h.digest(self.root / 'test-project/empty.fkproj'), receipt['seed_sha256'])
        self.assertEqual(h.digest(self.root / 'test-project/clip.mp4'), receipt['mp4_sha256'])
        with patch.object(h, 'executable', return_value='TEST-KACHINCO'), patch.object(h, 'run') as run:
            with self.assertRaises(FileExistsError):
                h.import_test(self.root / 'prepared/handoff.json', self.root / 'test-project', 'test-cli')
            run.assert_not_called()

    def test_changed_mp4_refused_before_cli_and_changed_timeline_fails_verification(self):
        self.prepare()
        invoke, _ = self.cli_boundary(corrupt=True)
        real_executable = h.executable
        with patch.object(h, 'run', side_effect=invoke), patch.object(h, 'executable',
                side_effect=lambda p: 'TEST-KACHINCO' if p == 'test-cli' else real_executable(p)):
            with self.assertRaisesRegex(ValueError, 'preservation'):
                h.import_test(self.root / 'prepared/handoff.json', self.root / 'test-project', 'test-cli')
        self.assertFalse(h.read_json(self.root / 'test-project/import-receipt.json')['success'])
        (self.root / 'prepared/clip.mp4').write_bytes(b'tampered')
        with patch.object(h, 'run') as run, self.assertRaisesRegex(ValueError, 'SHA-256'):
            h.import_test(self.root / 'prepared/handoff.json', self.root / 'bad-project', 'test-cli')
        run.assert_not_called()
        self.assertFalse((self.root / 'bad-project').exists())


if __name__ == '__main__':
    unittest.main()
