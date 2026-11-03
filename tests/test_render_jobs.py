"""Acceptance of durable authority, lost replies, backoff and owned cancellation."""
import copy
import json
from pathlib import Path
import struct
import sys
import tempfile
import urllib.error
from email.message import Message
from concurrent.futures import ThreadPoolExecutor
import unittest
from uuid import uuid4
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
from flamoris_cg.render_jobs import RenderJobs, JobConfig
from flamoris_cg.flamenco import BackendUnavailable, SubmissionRejected, Flamenco
from flamoris_cg.batch import apply_batch
from flamoris_cg.job_api import JobApi
from flamoris_cg.spec import load_scene


class Clock:
    def __init__(self): self.now=1000
    def __call__(self): return self.now
    def advance(self, seconds=31): self.now+=seconds


class Backend:
    def __init__(self):
        self.jobs={};self.posts=0;self.gets=0;self.finds=0;self.cancels=0
        self.lose_reply=False;self.unavailable=False;self.reject=False
    def job_type(self): return {'etag':'tested-etag'}
    def submit(self, payload):
        self.posts+=1
        if self.reject: raise SubmissionRejected('invalid_scene')
        job={**copy.deepcopy(payload),'id':str(uuid4()),'status':'queued',
             'steps_completed':0,'steps_total':3,'created':'server-created','updated':'server-updated'}
        self.jobs[job['id']]=job
        if self.lose_reply: raise BackendUnavailable('reply_lost',60)
        return copy.deepcopy(job)
    def get(self, identity):
        self.gets+=1
        if self.unavailable: raise BackendUnavailable('backend_http_429',120)
        return copy.deepcopy(self.jobs[identity])
    def find(self, namespace, identity):
        self.finds+=1
        return [copy.deepcopy(j) for j in self.jobs.values()
                if j['metadata']['flamoris.cg.namespace']==namespace and j['metadata']['flamoris.cg.job_id']==identity]
    def cancel(self, identity):
        self.cancels+=1;self.jobs[identity]['status']='canceled'
    def tasks(self, identity): return {'tasks':[]}
    def log_tail(self, identity): return ''


class RenderJobTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.clock=Clock();self.backend=Backend()
        self.config=JobConfig(self.root/'state',self.root/'shared','http://localhost:8080')
        self.api=RenderJobs(self.config,self.backend,self.clock)
        native=self.root/'source.blend';native.write_bytes(b'BLENDER-fixture-not-executed')
        self.meta={'scene_name':'Test','width':8,'height':8,'fps':24,'frame_start':1,'frame_end':240}
        self.api.register_scene('test-v1',native,self.meta)
        self.request={'request_id':str(uuid4()),'scene_id':'test-v1','frames':[1,2,3]}
    def submit(self): return self.api.submit(self.request)
    def complete(self, job, status='completed'):
        self.backend.jobs[job['backend_id']]['status']=status
        self.clock.advance()
        return self.api.status(job['job_id'])

    def test_returns_before_render_and_same_request_never_resubmits(self):
        job=self.submit();self.assertEqual(job['status'],'queued')
        self.assertEqual(self.api.submit(self.request)['job_id'],job['job_id'])
        self.assertEqual(self.backend.posts,1)
        self.assertEqual(self.backend.gets,0)

    def test_reconnect_uses_persisted_backend_identity(self):
        job=self.submit();self.clock.advance()
        again=RenderJobs(self.config,self.backend,self.clock)
        self.assertEqual(again.status(job['job_id'])['backend_id'],job['backend_id'])
        self.assertEqual(again.namespace,self.api.namespace)

    def test_lost_post_reply_is_reconciled_without_replay(self):
        self.backend.lose_reply=True
        job=self.submit();self.assertEqual(job['status'],'unknown')
        self.api.submit(self.request)
        self.assertEqual(self.backend.posts,1)
        self.clock.advance(61)
        again=RenderJobs(self.config,self.backend,self.clock)
        self.assertEqual(again.status(job['job_id'])['status'],'queued')
        self.assertEqual(self.backend.finds,1)
        self.assertEqual(self.backend.posts,1)

    def test_missing_or_duplicate_match_never_releases_unknown_capacity(self):
        self.backend.lose_reply=True;job=self.submit()
        remote=next(iter(self.backend.jobs.values()))
        self.backend.jobs[str(uuid4())]={**copy.deepcopy(remote),'id':str(uuid4())}
        self.clock.advance(61)
        self.assertEqual(self.api.status(job['job_id'])['status'],'unknown')
        self.assertEqual(self.backend.posts,1)
        with self.assertRaises(ValueError):
            self.api.submit({**self.request,'request_id':str(uuid4())})

    def test_conflicting_idempotency_key_rejected(self):
        self.submit()
        with self.assertRaises(ValueError): self.api.submit({**self.request,'frames':[1]})

    def test_frequent_status_calls_are_cached_and_429_backoff_is_durable(self):
        job=self.submit()
        for _ in range(50): self.api.status(job['job_id'])
        self.assertEqual(self.backend.gets,0)
        self.clock.advance();self.backend.unavailable=True
        result=self.api.status(job['job_id'])
        self.assertEqual(result['poll_after_seconds'],120)
        self.assertEqual(result['status'],'queued')
        again=RenderJobs(self.config,self.backend,self.clock)
        for _ in range(50): again.status(job['job_id'])
        self.assertEqual(self.backend.gets,1)

    def test_cancel_is_owned_idempotent_and_terminal_only_when_observed(self):
        job=self.submit();result=self.api.cancel(job['job_id'])
        self.assertEqual(result['status'],'canceling')
        self.api.cancel(job['job_id']);self.assertEqual(self.backend.cancels,1)
        self.clock.advance()
        self.assertEqual(self.api.status(job['job_id'])['status'],'canceled')

    def test_owner_mismatch_cannot_cancel_another_job(self):
        job=self.submit()
        self.backend.jobs[job['backend_id']]['metadata']['flamoris.cg.namespace']='other'
        self.assertIn('error',self.api.cancel(job['job_id']))
        self.assertEqual(self.backend.cancels,0)

    def test_failure_is_recorded_and_diagnostics_are_collectable(self):
        self.backend.reject=True;job=self.submit()
        self.assertEqual(job['status'],'failed')
        result=self.api.result(job['job_id']);self.assertTrue(result['ready'])
        with zipfile.ZipFile(self.api.artifact_path(job['job_id'])) as archive:
            self.assertEqual(json.loads(archive.read('job.json'))['error'],'invalid_scene')

    def test_success_verifies_all_frames_before_bulk_result(self):
        job=self.submit();self.complete(job)
        with self.assertRaises(ValueError): self.api.result(job['job_id'])
        header=b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR'+struct.pack('>II',8,8)
        for f in [1,2,3]:
            (self.config.shared_root/'jobs'/job['job_id']/'frames'/f'{f:06}.png').write_bytes(header)
        result=self.api.result(job['job_id']);self.assertTrue(result['ready'])
        self.assertEqual(result['sha256'],self.api.result(job['job_id'])['sha256'])

    def test_no_paths_code_urls_or_bad_numeric_values_in_request(self):
        for bad in [{'command':'echo bad'},{'manager_url':'http://evil'},
                    {'scene_id':'../secret'},{'frames':[True]},{'frames':[2,1]},
                    {'frames':[1,1]},{'chunk_size':False}]:
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                self.api.submit({**self.request,**bad})
        self.assertEqual(self.backend.posts,0)

    def test_changed_scene_rejected_before_post(self):
        (self.config.shared_root/'scenes/test-v1/scene.blend').write_bytes(b'changed')
        with self.assertRaises(ValueError):self.submit()
        self.assertEqual(self.backend.posts,0)

    def test_unknown_job_and_wrong_manager_cannot_access_state(self):
        with self.assertRaises(ValueError):self.api.status(str(uuid4()))
        with self.assertRaises(ValueError):RenderJobs(JobConfig(self.config.state_root,self.config.shared_root,'http://different'),self.backend)

    def test_concurrent_same_id_submits_once(self):
        with ThreadPoolExecutor(max_workers=4) as pool:
            jobs=list(pool.map(lambda _:RenderJobs(self.config,self.backend,self.clock).submit(self.request),range(4)))
        self.assertEqual(len({j['job_id'] for j in jobs}),1)
        self.assertEqual(self.backend.posts,1)

    def test_parallel_admission_is_bounded(self):
        self.submit()
        with self.assertRaises(ValueError):self.api.submit({**self.request,'request_id':str(uuid4())})

    def test_preflight_failure_does_not_leave_an_uncertain_submission(self):
        def unavailable():raise BackendUnavailable('backend_http_429',120)
        self.backend.job_type=unavailable
        job=self.submit()
        self.assertEqual(job['status'],'failed')
        self.assertTrue(job['terminal'])
        self.assertIsNone(job['poll_after_seconds'])
        self.assertEqual(self.backend.posts,0)

    def test_cancel_unknown_honors_backoff_before_requery(self):
        job=self.submit();self.backend.unavailable=True
        self.api.cancel(job['job_id'])
        for _ in range(20):self.api.cancel(job['job_id'])
        self.assertEqual(self.backend.gets,1)

    def test_quota_rejects_before_remote_submission(self):
        self.config=JobConfig(self.config.state_root,self.config.shared_root,'http://localhost:8080',max_output_bytes=1024)
        tiny=RenderJobs(self.config,self.backend,self.clock)
        with self.assertRaises(ValueError):tiny.submit(self.request)
        self.assertEqual(self.backend.posts,0)

    def test_symlink_artifact_is_rejected(self):
        job=self.submit();self.complete(job,'failed')
        path=self.config.shared_root/'jobs'/job['job_id']/'result.zip'
        try:path.symlink_to(self.root/'source.blend')
        except (OSError,NotImplementedError):self.skipTest('symlinks not available')
        with self.assertRaises(ValueError):self.api.result(job['job_id'])

    def test_retention_preserves_idempotency_and_never_prunes_active_job(self):
        job=self.submit()
        with self.assertRaises(ValueError):self.api.prune(job['job_id'])
        self.complete(job,'failed')
        with self.assertRaises(ValueError):self.api.prune(job['job_id'])
        self.clock.advance(7*24*3600+1)
        self.assertTrue(self.api.prune(job['job_id'])['purged'])
        self.assertTrue(self.api.submit(self.request)['purged'])
        self.assertEqual(self.backend.posts,1)
        self.assertTrue(self.api.result(job['job_id'])['expired'])

    def test_callable_boundary_excludes_operator_paths_and_maintenance(self):
        facade=JobApi(self.api)
        job=facade.call({'method':'render.submit','params':self.request})
        self.assertEqual(facade.call({'method':'job.status','params':{'job_id':job['job_id']}})['job_id'],job['job_id'])
        for request in [{'method':'register','params':{'path':'/etc/passwd'}},
                        {'method':'job.status','params':{'job_id':job['job_id'],'url':'http://evil'}},
                        {'method':'job.prune','params':{'job_id':job['job_id']}}]:
            with self.subTest(request=request),self.assertRaises(ValueError):facade.call(request)


class BatchTests(unittest.TestCase):
    def test_declared_batch_does_not_mutate_input(self):
        spec=load_scene(ROOT/'examples/hello_motion.json');before=copy.deepcopy(spec)
        batch=json.loads((ROOT/'examples/render_batch.json').read_text())
        changed,receipt=apply_batch(spec,batch)
        self.assertEqual(spec,before)
        self.assertEqual(changed['render']['width'],320)
        self.assertEqual(receipt['operations'],3)
        self.assertNotEqual(receipt['before_sha256'],receipt['after_sha256'])
    def test_invalid_last_operation_aborts_entire_batch(self):
        spec=load_scene(ROOT/'examples/hello_motion.json');before=copy.deepcopy(spec)
        batch={'schema_version':1,'operations':[
            {'type':'set_color','object_id':'red_ball','value':[0,1,0]},
            {'type':'set_location','object_id':'red_ball','value':[float('nan'),0,0]}]}
        with self.assertRaises(ValueError):apply_batch(spec,batch)
        self.assertEqual(spec,before)
    def test_arbitrary_bpy_and_unknown_object_rejected(self):
        spec=load_scene(ROOT/'examples/hello_motion.json')
        for op in [{'type':'python','value':'bpy.ops.wm.quit_blender()'},
                   {'type':'set_color','object_id':'missing','value':[0,0,0]}]:
            with self.subTest(op=op),self.assertRaises(ValueError):
                apply_batch(spec,{'schema_version':1,'operations':[op]})


class HttpPolicyTests(unittest.TestCase):
    def test_retry_after_survives_without_automatic_retry(self):
        backend=Flamenco('http://localhost:8080')
        calls=[]
        class Opener:
            def open(self, request, timeout):
                calls.append(request.full_url)
                headers=Message();headers['Retry-After']='120'
                raise urllib.error.HTTPError(request.full_url,429,'rate limited',headers,None)
        backend.opener=Opener()
        with self.assertRaises(BackendUnavailable) as error:
            backend.request('GET','/api/v3/version')
        self.assertEqual(error.exception.retry_after,120)
        self.assertEqual(len(calls),1)
    def test_origin_cannot_embed_credentials_or_extra_routes(self):
        for url in ['file:///tmp','http://user:password@host','http://host/path','http://host?token=secret']:
            with self.subTest(url=url),self.assertRaises(ValueError):Flamenco(url)
    def test_long_server_backoff_is_never_shortened(self):
        self.assertEqual(BackendUnavailable('rate_limited',7200).retry_after,7200)


if __name__=='__main__':unittest.main()
