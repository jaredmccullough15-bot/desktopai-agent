import json
from dotenv import load_dotenv
from modules.carriers.ambetter_worker import AmbetterWorker

load_dotenv()
worker = AmbetterWorker()
result = worker.run({"first_name":"Tony","last_name":"Adams","policy_id":"U73331298"})
print(json.dumps(result, indent=2))
