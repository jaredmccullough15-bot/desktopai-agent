import os
from datetime import datetime
import threading

class AgentLogger:
    _lock = threading.Lock()
    _log_dir = os.path.join(os.getcwd(), "agent_logs")

    @classmethod
    def log(cls, event_type, message, user=None, context=None, result=None):
        now = datetime.now()
        month_dir = os.path.join(cls._log_dir, now.strftime("%Y-%m"))
        os.makedirs(month_dir, exist_ok=True)
        log_file = os.path.join(month_dir, now.strftime("%Y-%m-%d") + ".log")
        timestamp = now.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        entry = f"[{timestamp}] [{event_type}]"
        if user:
            entry += f" [user:{user}]"
        if context:
            entry += f" [context:{context}]"
        if result:
            entry += f" [result:{result}]"
        entry += f" {message}\n"
        with cls._lock:
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(entry)
