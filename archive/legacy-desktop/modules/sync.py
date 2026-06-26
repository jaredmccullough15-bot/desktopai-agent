"""
Sync Module - Synchronizes learned patterns across multiple desktop installations.

This module enables shared learning by syncing observation data to a cloud-synced folder
(Google Drive, OneDrive, Dropbox, etc.). All instances can learn from each other.
"""

import os
import json
import time
import shutil
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime


class PatternSync:
    """Manages synchronization of learned patterns across installations."""
    
    def __init__(self, shared_path: Optional[str] = None):
        """
        Initialize pattern sync.
        
        Args:
            shared_path: Path to shared cloud folder (Google Drive, OneDrive, etc.)
                        If None, uses local-only mode (no sync)
        """
        self.shared_path = shared_path
        self.enabled = shared_path is not None and os.path.exists(shared_path)
        self.local_memory_file = os.path.join("data", "desktop_memory.json")
        self.shared_memory_file = None
        self.machine_id = self._get_machine_id()
        
        if self.enabled:
            self.shared_memory_file = os.path.join(shared_path, "shared_learning_patterns.json")
            # Create shared file if it doesn't exist
            if not os.path.exists(self.shared_memory_file):
                self._initialize_shared_file()
    
    def _get_machine_id(self) -> str:
        """Generate unique identifier for this machine."""
        try:
            import platform
            hostname = platform.node()
            username = os.getenv("USERNAME") or os.getenv("USER") or "unknown"
            return f"{username}@{hostname}"
        except Exception:
            return f"unknown-{int(time.time())}"
    
    def _initialize_shared_file(self):
        """Create initial shared patterns file."""
        if not self.enabled or not self.shared_memory_file:
            return
        
        try:
            os.makedirs(os.path.dirname(self.shared_memory_file), exist_ok=True)
            initial_data = {
                "learning_patterns": [],
                "machines": {},
                "last_sync": {},
                "metadata": {
                    "created": datetime.now().isoformat(),
                    "version": "1.0"
                }
            }
            with open(self.shared_memory_file, 'w') as f:
                json.dump(initial_data, f, indent=4)
        except Exception as e:
            print(f"⚠️ Could not initialize shared file: {e}")
            self.enabled = False
    
    def push_patterns_to_cloud(self) -> bool:
        """
        Push local learned patterns to shared cloud storage.
        Merges with existing patterns, keeping highest success counts.
        
        Returns:
            True if successful, False otherwise
        """
        if not self.enabled:
            return False
        
        try:
            # Load local patterns
            if not os.path.exists(self.local_memory_file):
                return False
            
            with open(self.local_memory_file, 'r') as f:
                local_memory = json.load(f)
            
            local_patterns = local_memory.get("learning_patterns", [])
            if not local_patterns:
                return True  # Nothing to push
            
            # Load shared patterns (with retry for concurrent access)
            shared_data = self._load_shared_data_safe()
            shared_patterns = shared_data.get("learning_patterns", [])
            
            # Merge patterns
            merged = self._merge_patterns(shared_patterns, local_patterns)
            
            # Update shared data
            shared_data["learning_patterns"] = merged
            shared_data["machines"][self.machine_id] = {
                "last_push": datetime.now().isoformat(),
                "pattern_count": len(local_patterns)
            }
            shared_data["last_sync"][self.machine_id] = time.time()
            
            # Save back to shared location
            self._save_shared_data_safe(shared_data)
            
            return True
        
        except Exception as e:
            print(f"⚠️ Sync push error: {e}")
            return False
    
    def pull_patterns_from_cloud(self) -> bool:
        """
        Pull learned patterns from shared cloud storage and merge with local.
        
        Returns:
            True if successful, False otherwise
        """
        if not self.enabled:
            return False
        
        try:
            # Load shared patterns
            shared_data = self._load_shared_data_safe()
            shared_patterns = shared_data.get("learning_patterns", [])
            
            if not shared_patterns:
                return True  # Nothing to pull
            
            # Load local patterns
            if os.path.exists(self.local_memory_file):
                with open(self.local_memory_file, 'r') as f:
                    local_memory = json.load(f)
            else:
                local_memory = {}
            
            local_patterns = local_memory.get("learning_patterns", [])
            
            # Merge patterns (shared takes priority if conflict)
            merged = self._merge_patterns(local_patterns, shared_patterns)
            
            # Update local memory
            local_memory["learning_patterns"] = merged
            
            # Save local
            os.makedirs(os.path.dirname(self.local_memory_file), exist_ok=True)
            with open(self.local_memory_file, 'w') as f:
                json.dump(local_memory, f, indent=4)
            
            return True
        
        except Exception as e:
            print(f"⚠️ Sync pull error: {e}")
            return False
    
    def sync_bidirectional(self) -> Dict[str, bool]:
        """
        Perform full bidirectional sync: pull, merge, then push.
        
        Returns:
            Dict with 'pull' and 'push' success status
        """
        if not self.enabled:
            return {"pull": False, "push": False}
        
        pull_ok = self.pull_patterns_from_cloud()
        push_ok = self.push_patterns_to_cloud()
        
        return {"pull": pull_ok, "push": push_ok}
    
    def _merge_patterns(self, base_patterns: List[Dict], new_patterns: List[Dict]) -> List[Dict]:
        """
        Merge two sets of learning patterns, keeping highest success counts.
        
        Args:
            base_patterns: Existing patterns
            new_patterns: Patterns to merge in
        
        Returns:
            Merged pattern list
        """
        # Create lookup dict for base patterns
        pattern_map = {}
        for pattern in base_patterns:
            key = self._pattern_key(pattern)
            pattern_map[key] = pattern
        
        # Merge in new patterns
        for new_pattern in new_patterns:
            key = self._pattern_key(new_pattern)
            
            if key in pattern_map:
                # Pattern exists - update with higher success count
                existing = pattern_map[key]
                new_success = new_pattern.get("success_count", 1)
                existing_success = existing.get("success_count", 1)
                
                if new_success > existing_success:
                    # New pattern is more successful, replace
                    pattern_map[key] = new_pattern
                else:
                    # Keep existing but update last_used if newer
                    new_last_used = new_pattern.get("last_used", 0)
                    if new_last_used > existing.get("last_used", 0):
                        existing["last_used"] = new_last_used
            else:
                # New pattern, add it
                pattern_map[key] = new_pattern
        
        # Convert back to list, sorted by success count
        merged = list(pattern_map.values())
        merged.sort(key=lambda p: p.get("success_count", 0), reverse=True)
        
        # Keep top 200 patterns (increased from 100 for shared learning)
        return merged[:200]
    
    def _pattern_key(self, pattern: Dict) -> str:
        """Generate unique key for a pattern."""
        pattern_type = pattern.get("pattern_type", "")
        context = pattern.get("context", "")
        solution = pattern.get("solution", "")
        return f"{pattern_type}||{context}||{solution}"
    
    def _load_shared_data_safe(self) -> Dict:
        """Load shared data with retry logic for concurrent access."""
        if not self.enabled or not self.shared_memory_file:
            return {}
        
        max_retries = 3
        for attempt in range(max_retries):
            try:
                with open(self.shared_memory_file, 'r') as f:
                    return json.load(f)
            except json.JSONDecodeError:
                # File might be mid-write, wait and retry
                time.sleep(0.5)
                if attempt == max_retries - 1:
                    # Return empty on final failure
                    return {
                        "learning_patterns": [],
                        "machines": {},
                        "last_sync": {},
                        "metadata": {}
                    }
            except Exception as e:
                if attempt == max_retries - 1:
                    print(f"⚠️ Could not load shared data: {e}")
                    return {}
                time.sleep(0.5)
        
        return {}
    
    def _save_shared_data_safe(self, data: Dict):
        """Save shared data with atomic write to prevent corruption."""
        if not self.enabled or not self.shared_memory_file:
            return
        
        try:
            # Write to temp file first
            temp_file = f"{self.shared_memory_file}.tmp"
            with open(temp_file, 'w') as f:
                json.dump(data, f, indent=4)
            
            # Atomic replace
            shutil.move(temp_file, self.shared_memory_file)
        
        except Exception as e:
            print(f"⚠️ Could not save shared data: {e}")
    
    def get_sync_status(self) -> Dict:
        """
        Get current sync status and statistics.
        
        Returns:
            Dict with sync info: enabled, machine_id, last_sync times, pattern counts, etc.
        """
        status = {
            "enabled": self.enabled,
            "machine_id": self.machine_id,
            "shared_path": self.shared_path,
        }
        
        if not self.enabled:
            status["message"] = "Sync disabled - no shared path configured"
            return status
        
        try:
            # Get local pattern count
            if os.path.exists(self.local_memory_file):
                with open(self.local_memory_file, 'r') as f:
                    local_memory = json.load(f)
                status["local_patterns"] = len(local_memory.get("learning_patterns", []))
            else:
                status["local_patterns"] = 0
            
            # Get shared data
            shared_data = self._load_shared_data_safe()
            status["shared_patterns"] = len(shared_data.get("learning_patterns", []))
            status["connected_machines"] = list(shared_data.get("machines", {}).keys())
            status["machine_count"] = len(shared_data.get("machines", {}))
            
            # Last sync time
            last_sync = shared_data.get("last_sync", {}).get(self.machine_id, 0)
            if last_sync:
                status["last_sync"] = datetime.fromtimestamp(last_sync).strftime("%Y-%m-%d %H:%M:%S")
            else:
                status["last_sync"] = "Never"
        
        except Exception as e:
            status["error"] = str(e)
        
        return status


# Global sync instance
_sync_instance = None


def get_sync_instance() -> PatternSync:
    """Get or create the global sync instance."""
    global _sync_instance
    if _sync_instance is None:
        from dotenv import load_dotenv
        load_dotenv()
        shared_path = os.getenv("SHARED_DATA_PATH")
        _sync_instance = PatternSync(shared_path)
    return _sync_instance


def sync_now() -> Dict[str, bool]:
    """Perform immediate bidirectional sync."""
    return get_sync_instance().sync_bidirectional()


def get_sync_status() -> Dict:
    """Get current sync status."""
    return get_sync_instance().get_sync_status()
