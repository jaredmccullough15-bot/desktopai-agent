import json, time, requests
BASE='http://bill-core-env.eba-e7menpcq.us-east-2.elasticbeanstalk.com'
MACHINE_UUID='26859f68-428b-402a-a7c0-93de924aa682'

r = requests.post(f"{BASE}/api/brain/workflow-learning/drafts", json={
    'workflow_name':'TrackVia E2E Teach Validation',
    'learning_path':'demonstration',
    'goal':'Validate rebuilt worker teach mode end-to-end',
    'source_text':''
}, timeout=30)
print('draft_status', r.status_code)
r.raise_for_status()
draft = r.json()
draft_id = draft.get('draft_id') or draft.get('id')
print('draft_id', draft_id)

r = requests.post(f"{BASE}/api/brain/workflow-learning/drafts/{draft_id}/teach-session/start", json={
    'start_url':'https://go.trackvia.com/#/signin',
    'api_base': BASE,
    'target_machine_uuid': MACHINE_UUID,
}, timeout=30)
print('start_status', r.status_code)
r.raise_for_status()
start = r.json()
print('start_body', json.dumps(start))
session_id = start.get('session_id')

status = None
for _ in range(24):
    time.sleep(2)
    sr = requests.get(f"{BASE}/api/teaching/session/{session_id}/status", timeout=20)
    if sr.status_code != 200:
        print('status_poll', sr.status_code, sr.text[:200])
        continue
    body = sr.json()
    status = body.get('status')
    print('status_poll', status, body.get('message','')[:120])
    if status in ('active','failed'):
        break

out = {'draft_id': draft_id, 'session_id': session_id, 'start': start, 'final_status': status}
with open('tmp_teach_e2e_result.json','w',encoding='utf-8') as f:
    json.dump(out,f,indent=2)
print('result_file', 'tmp_teach_e2e_result.json')
