import json, requests
BASE='http://bill-core-env.eba-e7menpcq.us-east-2.elasticbeanstalk.com'
SESSION='75f8236d-2e1e-48be-85cd-36c20b1047ab'

q = requests.get(f"{BASE}/api/teach-sessions/{SESSION}/questions/next?force=true", timeout=30)
print('question_status', q.status_code)
body = q.json()
print('question_has_prompt', bool((body or {}).get('question')))
print('question_body', json.dumps(body)[:800])

answer_result = {'skipped':'no_prompt'}
prompt = (body or {}).get('question') or {}
if prompt.get('prompt_id'):
    payload = {
        'prompt_id': prompt.get('prompt_id'),
        'step_order': body.get('step_order', 0),
        'answer': 'E2E validation note: entering credentials and submitting TrackVia sign-in.',
        'response_mode': 'text',
        'question_type': prompt.get('question_type', 'observation'),
        'trigger_type': prompt.get('trigger_type', 'manual'),
        'question_frequency': 'medium',
        'system_context': prompt.get('system_context') or {},
    }
    a = requests.post(f"{BASE}/api/teach-sessions/{SESSION}/answers", json=payload, timeout=30)
    print('answer_status', a.status_code)
    print('answer_body', a.text[:800])
    answer_result = {'status': a.status_code, 'body': a.json() if a.headers.get('content-type','').startswith('application/json') else a.text[:300]}

# Also verify action ingest path is alive for this session.
action_payload = {
  'action': {
    'id': 'e2e-action-1',
    'type': 'click',
    'selector': "button[type='submit']",
    'label': 'Sign In',
    'value_redacted': None,
    'url': 'https://go.trackvia.com/#/signin',
    'timestamp': '2026-05-22T11:48:00Z'
  },
  'step_id': None,
  'page_context': None,
}
ar = requests.post(f"{BASE}/api/teaching/session/{SESSION}/actions", json=action_payload, timeout=30)
print('action_status', ar.status_code)
print('action_body', ar.text[:400])

with open('tmp_teach_note_check.json','w',encoding='utf-8') as f:
    json.dump({'question_status':q.status_code,'question':body,'answer_result':answer_result,'action_status':ar.status_code,'action_body':ar.json() if ar.headers.get('content-type','').startswith('application/json') else ar.text}, f, indent=2)
print('result_file', 'tmp_teach_note_check.json')
