import time
from dotenv import load_dotenv
from modules.carriers.priority_health_worker import PriorityHealthWorker

load_dotenv()
worker = PriorityHealthWorker()
print({'starting': True, 'carrier': 'priority_health'})
result = worker.run({'first_name':'','last_name':'','dob':'','member_id':'','policy_id':''})
print({'result': result})
if getattr(worker, '_keep_browser_open_for_human', False):
    print({'mfa_human_mode': True, 'message': 'Browser intentionally left open for manual MFA help. Keeping process alive for 10 minutes.'})
    time.sleep(600)
print({'done': True})
