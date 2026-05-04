from collections import defaultdict
from datetime import UTC, datetime
from threading import Lock

from conversational.memory_models import EpisodicMemory, SemanticFact, WorkingMemoryTurn


class MemoryStore:
    def __init__(self) -> None:
        self._working_memory: dict[tuple[str, str], list[WorkingMemoryTurn]] = defaultdict(list)
        self._episodes: dict[tuple[str, str], list[EpisodicMemory]] = defaultdict(list)
        self._facts: dict[tuple[str, str], dict[str, SemanticFact]] = defaultdict(dict)
        self._lock = Lock()

    def add_turn(self, turn: WorkingMemoryTurn) -> WorkingMemoryTurn:
        key = (turn.tenant_id, turn.session_id)
        with self._lock:
            self._working_memory[key].append(turn)
        return turn

    def get_working_memory(self, tenant_id: str, session_id: str, limit: int = 20) -> list[WorkingMemoryTurn]:
        key = (tenant_id, session_id)
        safe_limit = max(1, limit)
        with self._lock:
            return list(self._working_memory.get(key, [])[-safe_limit:])

    def add_episode(self, episode: EpisodicMemory) -> EpisodicMemory:
        key = (episode.tenant_id, episode.session_id)
        with self._lock:
            self._episodes[key].append(episode)
        return episode

    def search_episodes(self, tenant_id: str, session_id: str, query: str, limit: int = 5) -> list[EpisodicMemory]:
        key = (tenant_id, session_id)
        safe_limit = max(1, limit)
        lowered_query = (query or "").lower()
        with self._lock:
            episodes = list(self._episodes.get(key, []))

        if not lowered_query:
            return episodes[-safe_limit:]

        matches = [
            item
            for item in episodes
            if lowered_query in item.summary.lower() or lowered_query in item.transcript.lower()
        ]
        return matches[-safe_limit:]

    def add_or_update_fact(self, fact: SemanticFact) -> SemanticFact:
        key = (fact.tenant_id, fact.session_id)
        with self._lock:
            existing = self._facts[key].get(fact.fact_key)
            if existing is None:
                self._facts[key][fact.fact_key] = fact
                return fact

            updated = existing.model_copy(update={"fact_value": fact.fact_value, "updated_at": datetime.now(UTC)})
            self._facts[key][fact.fact_key] = updated
            return updated

    def get_facts(self, tenant_id: str, session_id: str, limit: int = 20) -> list[SemanticFact]:
        key = (tenant_id, session_id)
        safe_limit = max(1, limit)
        with self._lock:
            values = list(self._facts.get(key, {}).values())
        return values[-safe_limit:]


memory_store = MemoryStore()
