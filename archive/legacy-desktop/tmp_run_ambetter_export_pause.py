import json
from dotenv import load_dotenv
from modules.carriers.ambetter_worker import AmbetterWorker

load_dotenv()
worker = AmbetterWorker()
result = worker.run_export_clients_csv(pause_after_export_click=True)
print(json.dumps(result, indent=2))
