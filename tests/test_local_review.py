import hashlib
import io
import json
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import local_model_review
import verify_local_run
import extract_jats_evidence


def sha(data):return hashlib.sha256(data).hexdigest()


class Reply:
    def __init__(self, value):self.stream = io.BytesIO(json.dumps(value).encode())
    def __enter__(self):return self
    def __exit__(self, *args):return False
    def read(self, n):return self.stream.read(n)


def setup(root):
    asset = root / 'asset.txt'; asset.write_text('synthetic source document')
    evidence = root / 'evidence.json'
    evidence.write_text(json.dumps({'source_sha256':sha(asset.read_bytes()), 'coverage':'selected_paragraphs',
                                    'anchors':{'xml-1':'Box plots for Hap1 and Hap2.'}}))
    task = {'task_id':'demo', 'question':'Summarize the comparison',
            'model':{'name':'demo:1b','sha256':'a'*64},
            'source':{'sha256':sha(asset.read_bytes()), 'scope':'eligible', 'identity_status':'verified',
                      'access_status':'allowed', 'held_asset_verified':True},
            'evidence_sha256':sha(evidence.read_bytes()),
            'endpoint':'http://127.0.0.1:11434',
            'limits':{'context_tokens':4096, 'output_tokens':256, 'timeout_seconds':5, 'threads':1}}
    taskpath=root/'task.json';taskpath.write_text(json.dumps(task))
    return taskpath,evidence,asset,task


def answer(reason='stop'):
    return {'done':True, 'done_reason':reason, 'message':{'content':json.dumps({'gene':'DEMO1',
        'observations':[{'trait':'grain weight','finding':'Hap2 has higher grain weight','comparison':'Hap2 versus Hap1',
                         'anchor':'xml-1','quote':'Box plots for Hap1 and Hap2'}]})}}


class LocalModelReviewTest(unittest.TestCase):
    def test_http_failure_retains_receipt_with_or_without_error_body(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            task, evidence, asset, _ = setup(root)
            for name, body in (('empty', None), ('body', io.BytesIO(b'failure'))):
                with self.subTest(name=name), patch.object(local_model_review.urllib.request, 'build_opener') as factory:
                    factory.return_value.open.side_effect = urllib.error.HTTPError('http://localhost', 503, 'failed', {}, body)
                    receipt = local_model_review.run(task, evidence, asset, root / name)
                self.assertEqual((receipt['status'], receipt['http_status']), ('model_service_failed', 503))
                self.assertTrue((root / name / 'run_receipt.json').exists())
                if body is not None:
                    self.assertTrue(body.closed)

    def test_model_response_is_bound_and_kept_pending(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);task,evidence,asset,_=setup(root)
            tags={'models':[{'name':'demo:1b','digest':'a'*64}]}
            with patch.object(local_model_review.urllib.request,'build_opener') as factory:
                op=factory.return_value;op.open.side_effect=[Reply(tags),Reply(answer()),Reply(tags)]
                rec=local_model_review.run(task,evidence,asset,root/'run')
                self.assertTrue(any(isinstance(item,local_model_review.NoRedirect) for item in factory.call_args.args))
                request=op.open.call_args_list[1].args[0]
                payload=json.loads(request.data)
            self.assertEqual(rec['status'],'pending_review')
            self.assertEqual(rec['result']['scientific_status'],'PENDING_INDEPENDENT_REVIEW')
            self.assertIn('direction_not_explicit_in_quote',rec['result']['checks'][0]['risk_flags'])
            self.assertFalse(payload['truncate']);self.assertFalse(payload['shift'])
            self.assertTrue((root/'run/response.raw').is_file())

    def test_offline_xml_to_model_candidate_and_handoff(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);asset=root/'article.xml'
            asset.write_text('<article><front><article-meta><article-id pub-id-type="doi">10.1234/target</article-id>'
                '<article-id pub-id-type="pmcid">PMC123</article-id></article-meta></front><body><sec><title>Results</title>'
                '<p>Box plots for Hap1 and Hap2. ' + ('synthetic text ' * 50) + '</p></sec></body></article>')
            extract_jats_evidence.run(asset,'10.1234/target','PMC123',root/'extract')
            evidence=root/'extract/evidence.json';taskpath,_,_,task=setup(root)
            task['source']['sha256']=sha(asset.read_bytes());task['evidence_sha256']=sha(evidence.read_bytes())
            taskpath.write_text(json.dumps(task))
            content={'gene':'DEMO1','observations':[{'trait':'grain weight','finding':'Hap2 has higher grain weight',
                'comparison':'Hap2 versus Hap1','anchor':'xml-00001','quote':'Box plots for Hap1 and Hap2'}]}
            reply={'done':True,'done_reason':'stop','message':{'content':json.dumps(content)}}
            tags={'models':[{'name':'demo:1b','digest':'a'*64}]}
            with patch.object(local_model_review.urllib.request,'build_opener') as factory:
                factory.return_value.open.side_effect=[Reply(tags),Reply(reply),Reply(tags)]
                rec=local_model_review.run(taskpath,evidence,asset,root/'model')
            self.assertEqual(rec['status'],'pending_review')
            self.assertIn('direction_not_explicit_in_quote',rec['result']['checks'][0]['risk_flags'])
            receipt=root/'model/run_receipt.json'
            self.assertEqual(verify_local_run.verify(receipt,sha(receipt.read_bytes()))['reuse_decision'],'REUSE_CANDIDATE_ONLY')

    def test_handoff_receipt_checks_all_inputs_and_detects_tampering(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);task,evidence,asset,_=setup(root);tags={'models':[{'name':'demo:1b','digest':'a'*64}]}
            with patch.object(local_model_review.urllib.request,'build_opener') as factory:
                factory.return_value.open.side_effect=[Reply(tags),Reply(answer()),Reply(tags)]
                local_model_review.run(task,evidence,asset,root/'run')
            receipt=root/'run/run_receipt.json';expected=sha(receipt.read_bytes())
            checked=verify_local_run.verify(receipt,expected)
            self.assertEqual(checked['reuse_decision'],'REUSE_CANDIDATE_ONLY')
            self.assertEqual(checked['scientific_status'],'PENDING_INDEPENDENT_REVIEW')
            asset.write_text('changed')
            with self.assertRaisesRegex(ValueError,'asset_hash_mismatch'):
                verify_local_run.verify(receipt,expected)

    def test_truncation_is_preserved_without_automatic_retry(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);task,evidence,asset,_=setup(root);tags={'models':[{'name':'demo:1b','digest':'a'*64}]}
            with patch.object(local_model_review.urllib.request,'build_opener') as factory:
                op=factory.return_value;op.open.side_effect=[Reply(tags),Reply(answer('length')),Reply(tags)]
                rec=local_model_review.run(task,evidence,asset,root/'run')
                self.assertEqual(op.open.call_count,3)
            self.assertEqual(rec['status'],'output_truncated')
            self.assertTrue((root/'run/response.raw').is_file())

    def test_truncated_retry_keeps_same_question_and_evidence(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);taskpath,evidence,asset,task=setup(root);tags={'models':[{'name':'demo:1b','digest':'a'*64}]}
            with patch.object(local_model_review.urllib.request,'build_opener') as factory:
                factory.return_value.open.side_effect=[Reply(tags),Reply(answer('length')),Reply(tags)]
                first=local_model_review.run(taskpath,evidence,asset,root/'first')
            self.assertEqual(first['status'],'output_truncated')
            old=root/'first/run_receipt.json'
            task['retry_of']={'receipt':str(old),'sha256':sha(old.read_bytes())}
            task['limits']['output_tokens']=512
            retry=root/'retry.json';retry.write_text(json.dumps(task))
            with patch.object(local_model_review.urllib.request,'build_opener') as factory:
                factory.return_value.open.side_effect=[Reply(tags),Reply(answer()),Reply(tags)]
                second=local_model_review.run(retry,evidence,asset,root/'retry')
            self.assertEqual(second['status'],'pending_review')
            task['question']='A different question';retry2=root/'retry2.json';retry2.write_text(json.dumps(task))
            with patch.object(local_model_review.urllib.request,'build_opener') as factory:
                rejected=local_model_review.run(retry2,evidence,asset,root/'rejected')
                factory.assert_not_called()
            self.assertEqual(rejected['status'],'invalid_task')

    def test_length_retry_is_bounded_to_one(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);taskpath,evidence,asset,task=setup(root);tags={'models':[{'name':'demo:1b','digest':'a'*64}]}
            with patch.object(local_model_review.urllib.request,'build_opener') as factory:
                factory.return_value.open.side_effect=[Reply(tags),Reply(answer('length')),Reply(tags)]
                local_model_review.run(taskpath,evidence,asset,root/'first')
            old=root/'first/run_receipt.json';task['retry_of']={'receipt':str(old),'sha256':sha(old.read_bytes())};task['limits']['output_tokens']=512
            retry=root/'retry.json';retry.write_text(json.dumps(task))
            with patch.object(local_model_review.urllib.request,'build_opener') as factory:
                factory.return_value.open.side_effect=[Reply(tags),Reply(answer('length')),Reply(tags)]
                second=local_model_review.run(retry,evidence,asset,root/'second')
            self.assertEqual(second['status'],'output_truncated')
            old2=root/'second/run_receipt.json';task['retry_of']={'receipt':str(old2),'sha256':sha(old2.read_bytes())};task['limits']['output_tokens']=1024
            third=root/'third.json';third.write_text(json.dumps(task))
            with patch.object(local_model_review.urllib.request,'build_opener') as factory:
                rejected=local_model_review.run(third,evidence,asset,root/'third')
                factory.assert_not_called()
            self.assertEqual(rejected['status'],'invalid_task')
            self.assertEqual(rejected['error'],'only_one_length_retry_allowed')

    def test_remote_endpoint_or_model_mismatch_stops_before_prompt(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);task,evidence,asset,config=setup(root)
            config['endpoint']='https://example.org';task.write_text(json.dumps(config))
            with patch.object(local_model_review.urllib.request,'build_opener') as factory:
                rec=local_model_review.run(task,evidence,asset,root/'remote')
                factory.assert_not_called()
            self.assertEqual(rec['status'],'invalid_task')
            config['endpoint']='http://127.0.0.1:11434';task.write_text(json.dumps(config))
            with patch.object(local_model_review.urllib.request,'build_opener') as factory:
                op=factory.return_value;op.open.return_value=Reply({'models':[{'name':'demo:1b','digest':'b'*64}]})
                rec=local_model_review.run(task,evidence,asset,root/'mismatch')
                self.assertEqual(op.open.call_count,1)
            self.assertEqual(rec['status'],'model_identity_mismatch')

    def test_code_drift_before_request_blocks_prompt(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);task,evidence,asset,_=setup(root);tags={'models':[{'name':'demo:1b','digest':'a'*64}]}
            original=local_model_review.digest;counts={}
            def changed(path):
                name=Path(path).name;counts[name]=counts.get(name,0)+1
                if name=='validate_review.py' and counts[name]>1:return '0'*64
                return original(path)
            with patch.object(local_model_review,'digest',side_effect=changed), patch.object(local_model_review.urllib.request,'build_opener') as factory:
                op=factory.return_value;op.open.return_value=Reply(tags)
                rec=local_model_review.run(task,evidence,asset,root/'run')
                self.assertEqual(op.open.call_count,1)
            self.assertEqual(rec['status'],'code_changed')
            self.assertFalse((root/'run/request.json').exists())

    def test_input_change_during_model_call_blocks_validation(self):
        class ChangedReply(Reply):
            def __init__(self, value, evidence):super().__init__(value);self.evidence=evidence
            def read(self,n):
                self.evidence.write_text('{}')
                return super().read(n)
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);task,evidence,asset,_=setup(root);tags={'models':[{'name':'demo:1b','digest':'a'*64}]}
            with patch.object(local_model_review.urllib.request,'build_opener') as factory:
                factory.return_value.open.side_effect=[Reply(tags),ChangedReply(answer(),evidence),Reply(tags)]
                rec=local_model_review.run(task,evidence,asset,root/'run')
            self.assertEqual(rec['status'],'input_changed')
            self.assertTrue((root/'run/response.raw').is_file())
            self.assertFalse((root/'run/validation').exists())

    def test_interrupted_response_keeps_partial_and_failure_receipt(self):
        class Interrupted:
            def __init__(self):self.count=0
            def __enter__(self):return self
            def __exit__(self,*args):return False
            def read(self,n):
                self.count += 1
                if self.count == 1:return b'{"unfinished":'
                raise OSError('synthetic interruption')
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);task,evidence,asset,_=setup(root);tags={'models':[{'name':'demo:1b','digest':'a'*64}]}
            with patch.object(local_model_review.urllib.request,'build_opener') as factory:
                factory.return_value.open.side_effect=[Reply(tags),Interrupted()]
                rec=local_model_review.run(task,evidence,asset,root/'run')
            self.assertEqual(rec['status'],'model_service_failed')
            self.assertEqual((root/'run/response.raw.partial').read_bytes(),b'{"unfinished":')
            self.assertTrue((root/'run/run_receipt.json').is_file())

    def test_held_asset_can_be_reused_during_access_stop(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);task,evidence,asset,config=setup(root);config['source']['access_status']='stopped';task.write_text(json.dumps(config))
            tags={'models':[{'name':'demo:1b','digest':'a'*64}]}
            with patch.object(local_model_review.urllib.request,'build_opener') as factory:
                factory.return_value.open.side_effect=[Reply(tags),Reply(answer()),Reply(tags)]
                rec=local_model_review.run(task,evidence,asset,root/'run')
            self.assertEqual(rec['status'],'pending_review')
            self.assertEqual(rec['source_access'],'stopped_held_asset_reused')


if __name__=='__main__':unittest.main()
