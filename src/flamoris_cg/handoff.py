"""Offline, explicitly selected render result -> MP4 -> NEW Kachinco test project.

No scheduler, network, live editor, project codec or timeline authority here.
Only the installed Kachinco CLI creates and imports projects.
"""
from contextlib import ExitStack
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import stat
import struct
import subprocess
import tempfile
import zipfile

from .render_jobs import checked_uuid, contained, digest, integer
from .spec import _no_duplicate_pairs, _no_constant

MAX_BYTES = 512 * 1024 * 1024
TICKS = 35_280_000


def decode(raw):
    return json.loads(raw.decode('utf-8'), object_pairs_hook=_no_duplicate_pairs,
                      parse_constant=_no_constant)


def read_json(path):
    with Path(path).open('rb') as stream:
        raw = stream.read(1024 * 1024 + 1)
    if len(raw) > 1024 * 1024:
        raise ValueError('JSON byte limit')
    return decode(raw)


def write_json(path, value):
    with Path(path).open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, allow_nan=False, indent=2)
        stream.write('\n')


def fraction(value):
    return {'numerator': str(value.numerator), 'denominator': str(value.denominator)}


def timing(scene, frames):
    if not isinstance(frames, list) or not 1 <= len(frames) <= 240:
        raise ValueError('1..240 consecutive frames required')
    for frame in frames:
        integer(frame, 1, 999999)
    if frames != list(range(frames[0], frames[0] + len(frames))):
        raise ValueError('sparse, duplicate or unordered frames are not a video')
    integer(scene['width'], 2, 1920)
    integer(scene['height'], 2, 1080)
    if scene['width'] % 2 or scene['height'] % 2:
        raise ValueError('H.264/yuv420p requires even dimensions; no implicit resize')
    if (type(scene['fps']) not in (int, float) or not math.isfinite(scene['fps'])
            or not 1 <= scene['fps'] <= 120):
        raise ValueError('invalid JOB fps')
    # Preserve the registered decimal value; never guess an NTSC rate.
    fps = Fraction(str(scene['fps']))
    if fps.denominator > 1_000_000 or fps.numerator > 2_147_483_647:
        raise ValueError('JOB fps is outside the exact MP4 timebase subset')
    integer(scene['frame_start'], 1, frames[0])
    integer(scene['frame_end'], frames[-1], 1_000_000)
    return fps, Fraction(len(frames), 1) / fps


def executable(path):
    resolved = shutil.which(str(path))
    if resolved is None:
        raise ValueError('executable not found: ' + str(path))
    return str(Path(resolved).absolute())


def run(command, log, *, timeout=300, error_log=None):
    """Fixed argv only. Logs are retained; a timeout never triggers a replay."""
    with ExitStack() as stack:
        stream = stack.enter_context(Path(log).open('xb'))
        errors = (stack.enter_context(Path(error_log).open('xb'))
                  if error_log is not None else subprocess.STDOUT)
        result = subprocess.run(command, stdin=subprocess.DEVNULL, stdout=stream,
                                stderr=errors, timeout=timeout, check=False)
    if result.returncode:
        raise ValueError('command failed; inspect ' + str(log))


def verify_video(path, scene, frames, probe, log):
    fps, duration = timing(scene, frames)
    run([probe, '-v', 'error', '-count_frames', '-show_streams', '-show_format',
         '-of', 'json', str(path)], log, timeout=120)
    report = read_json(log)
    streams = report.get('streams', [])
    if len(streams) != 1:
        raise ValueError('exactly one video stream and no audio required')
    s = streams[0]
    if (s.get('codec_type') != 'video' or s.get('codec_name') != 'h264'
            or s.get('pix_fmt') != 'yuv420p'
            or (s.get('width'), s.get('height')) != (scene['width'], scene['height'])
            or int(s.get('nb_read_frames', 0)) != len(frames)
            or int(s.get('nb_frames', 0)) != len(frames)
            or Fraction(s.get('avg_frame_rate', '0')) != fps
            or Fraction(s.get('r_frame_rate', '0')) != fps):
        raise ValueError('MP4 codec/dimensions/decoded count/FPS mismatch')
    # Stream duration is exact in the selected MP4 timescale. Container decimal
    # duration can be rounded to milliseconds by the muxer.
    if (int(s.get('duration_ts', 0)) * Fraction(s.get('time_base', '0')) != duration
            or abs(Fraction(report['format']['duration']) - duration) > Fraction(1, 1000)):
        raise ValueError('MP4 duration mismatch')
    if not 0 < Path(path).stat().st_size <= MAX_BYTES:
        raise ValueError('MP4 byte limit')
    return report


def new_directory(path):
    path = Path(path).absolute()
    contained(path, path)  # Includes all existing parents, before mkdir.
    path.mkdir(exist_ok=False)  # Parent must already exist; no reuse or overwrite.
    return path


def prepare(result_zip, job_id, result_sha256, output, ffmpeg='ffmpeg', ffprobe='ffprobe'):
    checked_uuid(job_id)
    if not isinstance(result_sha256, str) or not re.fullmatch('[0-9a-f]{64}', result_sha256):
        raise ValueError('lowercase result SHA-256 required from cg.job_result')
    source = Path(result_zip).absolute()
    contained(source.parent, source)
    if not source.is_file() or not 0 < source.stat().st_size <= MAX_BYTES:
        raise ValueError('result ZIP byte limit')
    encoder, probe = executable(ffmpeg), executable(ffprobe)
    # Open one source handle and hash those same bytes before consuming them.
    with source.open('rb') as stream:
        if hashlib.file_digest(stream, 'sha256').hexdigest() != result_sha256:
            raise ValueError('result ZIP SHA-256 mismatch')
        stream.seek(0)
        with zipfile.ZipFile(stream) as archive:
            members = archive.infolist()
            names = [m.filename for m in members]
            if len(names) > 242 or len(set(names)) != len(names):
                raise ValueError('duplicate/excess ZIP members')
            for m in members:
                kind = stat.S_IFMT(m.external_attr >> 16)
                if (m.flag_bits & 1 or kind not in (0, stat.S_IFREG)
                        or m.file_size < 0 or m.file_size > MAX_BYTES):
                    raise ValueError('unsupported ZIP member')
            if sum(m.file_size for m in members) > MAX_BYTES:
                raise ValueError('expanded result byte limit')
            if 'job.json' not in names or archive.getinfo('job.json').file_size > 256 * 1024:
                raise ValueError('bounded job.json required')
            job = decode(archive.read('job.json'))
            if (job['job_id'] != job_id or job['status'] != 'succeeded' or job.get('purged')
                    or job.get('cancel_requested')):
                raise ValueError('selected JOB must be successful, retained and not canceled')
            scene, frames = job['scene'], job['request']['frames']
            fps, duration = timing(scene, frames)
            expected = {'job.json', 'diagnostics.json'} | {f'frames/{f:06d}.png' for f in frames}
            if set(names) != expected:
                raise ValueError('ZIP must contain exactly the selected JOB frames and diagnostics')
            folder = new_directory(output)
            receipt = {'schema_version': 1, 'success': False, 'job_id': job_id,
                       'implementation_sha256': digest(Path(__file__)),
                       'result_sha256': result_sha256, 'scene': scene, 'frames': frames,
                       'fps': fraction(fps), 'duration_seconds': fraction(duration),
                       'duration_ticks_exact': fraction(duration * TICKS),
                       'alpha': 'composited over black; opaque output', 'audio': False}
            try:
                with tempfile.TemporaryDirectory(prefix='.frames-', dir=folder) as staging:
                    staging = Path(staging)
                    hashes = {}
                    for frame in frames:
                        name = f'frames/{frame:06d}.png'
                        data = archive.read(name)  # ZIP CRC checked; no extract/extractall.
                        if (len(data) < 24 or data[:16] != b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR'
                                or struct.unpack('>II', data[16:24]) != (scene['width'], scene['height'])):
                            raise ValueError('PNG header/dimensions mismatch')
                        hashes[name] = hashlib.sha256(data).hexdigest()
                        (staging / f'{frame:06d}.png').write_bytes(data)
                    receipt['frame_sha256'] = hashes
                    video = folder / 'clip.mp4'
                    command = [encoder, '-nostdin', '-v', 'error', '-n', '-threads', '2',
                        '-f', 'lavfi', '-i', f"color=c=black:s={scene['width']}x{scene['height']}:r={fps}",
                        '-framerate', str(fps), '-start_number', str(frames[0]), '-threads', '2',
                        '-i', str(staging / '%06d.png'), '-filter_complex_threads', '2',
                        '-filter_complex', '[0:v][1:v]overlay=shortest=1:format=auto,format=yuv420p',
                        '-frames:v', str(len(frames)), '-an', '-c:v', 'libx264', '-threads', '2',
                        '-crf', '20', '-fs', str(MAX_BYTES), '-video_track_timescale', str(fps.numerator),
                        '-movflags', '+faststart', str(video)]
                    receipt['encode_command'] = command
                    run(command, folder / 'ffmpeg.log')
                    verify_video(video, scene, frames, probe, folder / 'ffprobe.json')
                    # Detect source changes during collection; caller-controlled
                    # input/output directories must not have concurrent writers.
                    if digest(source) != result_sha256:
                        raise ValueError('result ZIP changed during preparation')
                    receipt.update(mp4_sha256=digest(video), mp4_bytes=video.stat().st_size)
                    run([encoder, '-version'], folder / 'ffmpeg-version.txt', timeout=10)
                    run([probe, '-version'], folder / 'ffprobe-version.txt', timeout=10)
                    receipt['success'] = True
            except (Exception, KeyboardInterrupt) as exc:
                receipt['error'] = type(exc).__name__ + ': ' + str(exc)
                raise
            finally:
                write_json(folder / 'handoff.json', receipt)
    return receipt


def import_test(handoff, output, kachinco, ffprobe='ffprobe'):
    """Always create a fresh seed; no existing-project argument is supported."""
    handoff = Path(handoff).absolute()
    contained(handoff.parent, handoff)
    receipt = read_json(handoff)
    if receipt.get('schema_version') != 1 or receipt.get('success') is not True:
        raise ValueError('successful handoff receipt required')
    checked_uuid(receipt['job_id'])
    scene, frames = receipt['scene'], receipt['frames']
    fps, duration = timing(scene, frames)
    if receipt['fps'] != fraction(fps) or receipt['duration_seconds'] != fraction(duration):
        raise ValueError('handoff timing mismatch')
    source = contained(handoff.parent, handoff.parent / 'clip.mp4')
    if not 0 < source.stat().st_size <= MAX_BYTES or digest(source) != receipt['mp4_sha256']:
        raise ValueError('MP4 SHA-256 mismatch before import')
    cli, probe = executable(kachinco), executable(ffprobe)
    folder = new_directory(output)
    result = {'schema_version': 1, 'success': False, 'job_id': receipt['job_id'],
              'implementation_sha256': digest(Path(__file__)),
              'mp4_sha256': receipt['mp4_sha256'], 'commands': []}
    try:
        video = folder / 'clip.mp4'
        with source.open('rb') as src, video.open('xb') as dest:
            shutil.copyfileobj(src, dest)
        if digest(video) != receipt['mp4_sha256']:
            raise ValueError('MP4 changed while copying')
        verify_video(video, scene, frames, probe, folder / 'ffprobe.json')
        seed, imported = folder / 'empty.fkproj', folder / 'imported.fkproj'

        def invoke(args, log):
            command = [cli, *map(str, args)]
            result['commands'].append(command)
            # CLI contract: stdout is JSON, stderr is diagnostics even on success.
            run(command, folder / log, timeout=120, error_log=folder / (log + '.stderr'))
            return read_json(folder / log)

        invoke(['project', 'new', '--output', seed, '--name', 'CG handoff TEST',
                '--width', scene['width'], '--height', scene['height'],
                '--duration', math.ceil(duration)], 'new.json')
        seed_hash = digest(seed)
        before = invoke(['project', 'info', seed, '--json'], 'before.json')
        before_project = before['project']['project']
        if before_project['assets'] or before['media']:
            raise ValueError('new test seed must be empty')
        invoke(['media', 'import', seed, '--source', video, '--output', imported], 'import.json')
        if digest(seed) != seed_hash or digest(video) != receipt['mp4_sha256']:
            raise ValueError('source seed/media changed during import')
        validation = invoke(['project', 'validate', imported, '--json'], 'validate.json')
        after = invoke(['project', 'info', imported, '--json'], 'after.json')  # Reopen from disk.
        p = after['project']['project']
        assets = p['assets']
        if (validation.get('valid') is not True or len(assets) != 1 or len(after['media']) != 1
                or after['media'][0]['isAvailable'] is not True
                or Path(after['media'][0]['resolvedPath']).resolve() != video.resolve()
                or {k: v for k, v in p.items() if k != 'assets'} !=
                   {k: v for k, v in before_project.items() if k != 'assets'}
                or after['project']['authoring'] != before['project']['authoring']
                or after['project']['generatedAssets'] != before['project']['generatedAssets']
                or assets[0]['kind'] != 'Mov'
                or abs(Fraction(int(assets[0]['durationTicks']), TICKS) - duration) > Fraction(1, 1000)):
            raise ValueError('import/reopen/preservation verification failed')
        result.update(success=True, project=imported.name, seed_sha256=seed_hash,
                      project_sha256=digest(imported), media_asset_id=assets[0]['id'],
                      revision_before=before['revision'], revision_after=after['revision'],
                      note='Media registered only. No timeline placement, preview or final export.')
    except (Exception, KeyboardInterrupt) as exc:
        result['error'] = type(exc).__name__ + ': ' + str(exc)
        raise
    finally:
        write_json(folder / 'import-receipt.json', result)
    return result
