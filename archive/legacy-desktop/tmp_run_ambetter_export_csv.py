import json
from dotenv import load_dotenv
from modules.carriers.ambetter_worker import AmbetterWorker

load_dotenv()
worker = AmbetterWorker()
result = worker.run_export_clients_csv()
print(json.dumps(result, indent=2))
