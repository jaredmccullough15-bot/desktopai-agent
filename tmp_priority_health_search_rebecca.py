from dotenv import load_dotenv
from modules.carriers.priority_health_worker import PriorityHealthWorker

load_dotenv()
worker = PriorityHealthWorker()
result = worker.run({
    'first_name': 'Rebecca',
    'last_name': 'McCullough',
    'dob': '',
    'member_id': '',
    'policy_id': '',
})
print({'query': 'Rebecca McCullough', 'result': result})
