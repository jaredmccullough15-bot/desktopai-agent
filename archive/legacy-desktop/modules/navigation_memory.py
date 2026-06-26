import json
import os
import sqlite3
import time
from typing import Any


DEFAULT_DB_PATH = os.path.join("data", "navigation_memory.db")


class NavigationMemoryStore:
    def __init__(self, db_path: str = DEFAULT_DB_PATH) -> None:
        self.db_path = db_path
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS site_profiles (
                    site_name TEXT NOT NULL,
                    url_pattern TEXT NOT NULL,
                    goal TEXT NOT NULL,
                    popup_behavior TEXT,
                    iframe_notes TEXT,
                    shadow_dom_notes TEXT,
                    download_behavior TEXT,
                    last_success_ts REAL,
                    success_count INTEGER DEFAULT 0,
                    failure_count INTEGER DEFAULT 0,
                    confidence REAL DEFAULT 0.0,
                    trusted INTEGER DEFAULT 0,
                    meta_json TEXT,
                    PRIMARY KEY (site_name, url_pattern, goal)
                );

                CREATE TABLE IF NOT EXISTS selector_memory (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    site_name TEXT NOT NULL,
                    url_pattern TEXT NOT NULL,
                    goal TEXT NOT NULL,
                    action_name TEXT NOT NULL,
                    selector_type TEXT NOT NULL,
                    selector_value TEXT NOT NULL,
                    wait_condition TEXT,
                    fallback_method TEXT,
                    success_count INTEGER DEFAULT 0,
                    failure_count INTEGER DEFAULT 0,
                    confidence REAL DEFAULT 0.0,
                    trusted INTEGER DEFAULT 0,
                    last_success_ts REAL,
                    last_failure_ts REAL,
                    notes_json TEXT,
                    UNIQUE (site_name, url_pattern, goal, action_name, selector_type, selector_value)
                );

                CREATE TABLE IF NOT EXISTS recovery_patterns (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    site_name TEXT NOT NULL,
                    url_pattern TEXT NOT NULL,
                    failure_class TEXT NOT NULL,
                    recovery_strategy TEXT NOT NULL,
                    success_count INTEGER DEFAULT 0,
                    failure_count INTEGER DEFAULT 0,
                    confidence REAL DEFAULT 0.0,
                    trusted INTEGER DEFAULT 0,
                    last_success_ts REAL,
                    last_failure_ts REAL,
                    UNIQUE (site_name, url_pattern, failure_class, recovery_strategy)
                );

                CREATE TABLE IF NOT EXISTS task_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp REAL NOT NULL,
                    site_name TEXT,
                    url TEXT,
                    goal TEXT,
                    status TEXT,
                    failure_class TEXT,
                    details_json TEXT
                );
                """
            )

    @staticmethod
    def _confidence(success_count: int, failure_count: int) -> float:
        total = max(1, success_count + failure_count)
        return round(success_count / total, 4)

    @staticmethod
    def _trusted(success_count: int, confidence: float) -> int:
        return 1 if success_count >= 3 and confidence >= 0.75 else 0

    def upsert_site_profile(
        self,
        site_name: str,
        url_pattern: str,
        goal: str,
        popup_behavior: str = "",
        iframe_notes: str = "",
        shadow_dom_notes: str = "",
        download_behavior: str = "",
        meta: dict[str, Any] | None = None,
    ) -> None:
        with self._connect() as conn:
            existing = conn.execute(
                "SELECT * FROM site_profiles WHERE site_name=? AND url_pattern=? AND goal=?",
                (site_name, url_pattern, goal),
            ).fetchone()
            if existing:
                conn.execute(
                    """
                    UPDATE site_profiles
                    SET popup_behavior=?, iframe_notes=?, shadow_dom_notes=?, download_behavior=?, meta_json=?
                    WHERE site_name=? AND url_pattern=? AND goal=?
                    """,
                    (
                        popup_behavior,
                        iframe_notes,
                        shadow_dom_notes,
                        download_behavior,
                        json.dumps(meta or {}),
                        site_name,
                        url_pattern,
                        goal,
                    ),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO site_profiles (
                        site_name, url_pattern, goal, popup_behavior, iframe_notes,
                        shadow_dom_notes, download_behavior, meta_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        site_name,
                        url_pattern,
                        goal,
                        popup_behavior,
                        iframe_notes,
                        shadow_dom_notes,
                        download_behavior,
                        json.dumps(meta or {}),
                    ),
                )

    def mark_site_outcome(self, site_name: str, url_pattern: str, goal: str, success: bool) -> None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT success_count, failure_count FROM site_profiles WHERE site_name=? AND url_pattern=? AND goal=?",
                (site_name, url_pattern, goal),
            ).fetchone()
            if not row:
                self.upsert_site_profile(site_name, url_pattern, goal)
                row = {"success_count": 0, "failure_count": 0}

            success_count = int(row["success_count"]) + (1 if success else 0)
            failure_count = int(row["failure_count"]) + (0 if success else 1)
            confidence = self._confidence(success_count, failure_count)
            trusted = self._trusted(success_count, confidence)

            conn.execute(
                """
                UPDATE site_profiles
                SET success_count=?, failure_count=?, confidence=?, trusted=?, last_success_ts=?
                WHERE site_name=? AND url_pattern=? AND goal=?
                """,
                (
                    success_count,
                    failure_count,
                    confidence,
                    trusted,
                    time.time() if success else None,
                    site_name,
                    url_pattern,
                    goal,
                ),
            )

    def record_selector_outcome(
        self,
        site_name: str,
        url_pattern: str,
        goal: str,
        action_name: str,
        selector_type: str,
        selector_value: str,
        wait_condition: str = "",
        fallback_method: str = "",
        success: bool = True,
        notes: dict[str, Any] | None = None,
    ) -> None:
        now = time.time()
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM selector_memory
                WHERE site_name=? AND url_pattern=? AND goal=? AND action_name=? AND selector_type=? AND selector_value=?
                """,
                (site_name, url_pattern, goal, action_name, selector_type, selector_value),
            ).fetchone()

            if row:
                success_count = int(row["success_count"]) + (1 if success else 0)
                failure_count = int(row["failure_count"]) + (0 if success else 1)
                confidence = self._confidence(success_count, failure_count)
                trusted = self._trusted(success_count, confidence)
                conn.execute(
                    """
                    UPDATE selector_memory
                    SET wait_condition=?, fallback_method=?, success_count=?, failure_count=?,
                        confidence=?, trusted=?, last_success_ts=?, last_failure_ts=?, notes_json=?
                    WHERE id=?
                    """,
                    (
                        wait_condition,
                        fallback_method,
                        success_count,
                        failure_count,
                        confidence,
                        trusted,
                        now if success else row["last_success_ts"],
                        now if not success else row["last_failure_ts"],
                        json.dumps(notes or {}),
                        row["id"],
                    ),
                )
            else:
                success_count = 1 if success else 0
                failure_count = 0 if success else 1
                confidence = self._confidence(success_count, failure_count)
                trusted = self._trusted(success_count, confidence)
                conn.execute(
                    """
                    INSERT INTO selector_memory (
                        site_name, url_pattern, goal, action_name, selector_type, selector_value,
                        wait_condition, fallback_method, success_count, failure_count, confidence,
                        trusted, last_success_ts, last_failure_ts, notes_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        site_name,
                        url_pattern,
                        goal,
                        action_name,
                        selector_type,
                        selector_value,
                        wait_condition,
                        fallback_method,
                        success_count,
                        failure_count,
                        confidence,
                        trusted,
                        now if success else None,
                        now if not success else None,
                        json.dumps(notes or {}),
                    ),
                )

    def get_selector_candidates(
        self,
        site_name: str,
        url_pattern: str,
        goal: str,
        action_name: str,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM selector_memory
                WHERE site_name=? AND url_pattern=? AND goal=? AND action_name=?
                ORDER BY trusted DESC, confidence DESC, success_count DESC, last_success_ts DESC
                LIMIT ?
                """,
                (site_name, url_pattern, goal, action_name, limit),
            ).fetchall()
            return [dict(r) for r in rows]

    def record_recovery_outcome(
        self,
        site_name: str,
        url_pattern: str,
        failure_class: str,
        recovery_strategy: str,
        success: bool,
    ) -> None:
        now = time.time()
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM recovery_patterns
                WHERE site_name=? AND url_pattern=? AND failure_class=? AND recovery_strategy=?
                """,
                (site_name, url_pattern, failure_class, recovery_strategy),
            ).fetchone()

            if row:
                success_count = int(row["success_count"]) + (1 if success else 0)
                failure_count = int(row["failure_count"]) + (0 if success else 1)
                confidence = self._confidence(success_count, failure_count)
                trusted = self._trusted(success_count, confidence)
                conn.execute(
                    """
                    UPDATE recovery_patterns
                    SET success_count=?, failure_count=?, confidence=?, trusted=?,
                        last_success_ts=?, last_failure_ts=?
                    WHERE id=?
                    """,
                    (
                        success_count,
                        failure_count,
                        confidence,
                        trusted,
                        now if success else row["last_success_ts"],
                        now if not success else row["last_failure_ts"],
                        row["id"],
                    ),
                )
            else:
                success_count = 1 if success else 0
                failure_count = 0 if success else 1
                confidence = self._confidence(success_count, failure_count)
                trusted = self._trusted(success_count, confidence)
                conn.execute(
                    """
                    INSERT INTO recovery_patterns (
                        site_name, url_pattern, failure_class, recovery_strategy,
                        success_count, failure_count, confidence, trusted,
                        last_success_ts, last_failure_ts
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        site_name,
                        url_pattern,
                        failure_class,
                        recovery_strategy,
                        success_count,
                        failure_count,
                        confidence,
                        trusted,
                        now if success else None,
                        now if not success else None,
                    ),
                )

    def get_recovery_candidates(
        self,
        site_name: str,
        url_pattern: str,
        failure_class: str,
        limit: int = 6,
    ) -> list[str]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT recovery_strategy FROM recovery_patterns
                WHERE site_name=? AND url_pattern=? AND failure_class=?
                ORDER BY trusted DESC, confidence DESC, success_count DESC, last_success_ts DESC
                LIMIT ?
                """,
                (site_name, url_pattern, failure_class, limit),
            ).fetchall()
            return [str(r["recovery_strategy"]) for r in rows]

    def add_task_history(
        self,
        site_name: str,
        url: str,
        goal: str,
        status: str,
        failure_class: str = "",
        details: dict[str, Any] | None = None,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO task_history (timestamp, site_name, url, goal, status, failure_class, details_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (time.time(), site_name, url, goal, status, failure_class, json.dumps(details or {})),
            )

    def get_recent_task_history(self, limit: int = 20) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM task_history ORDER BY timestamp DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]
