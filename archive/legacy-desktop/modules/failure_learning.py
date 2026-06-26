"""
Failure Learning & Auto-Recovery Module

Tracks failed actions, learns from them, and suggests/attempts recovery strategies.
"""

import os
import json
import time
from datetime import datetime
from typing import List, Dict, Optional, Tuple


class FailureLearningSystem:
    """Manages failure tracking, learning, and auto-recovery strategies."""
    
    def __init__(self):
        """Initialize failure learning system."""
        self.failure_file = os.path.join(os.path.dirname(__file__), "..", "data", "failure_history.json")
        self.recovery_file = os.path.join(os.path.dirname(__file__), "..", "data", "recovery_strategies.json")
        self.failures = []
        self.recovery_strategies = []
        self.load_data()
    
    def load_data(self):
        """Load failure history and recovery strategies from files."""
        # Load failure history
        try:
            if os.path.exists(self.failure_file):
                with open(self.failure_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.failures = data.get("failures", [])
                    # Keep only recent failures (last 200)
                    self.failures = self.failures[-200:]
        except Exception as e:
            print(f"Failed to load failure history: {e}")
            self.failures = []
        
        # Load recovery strategies
        try:
            if os.path.exists(self.recovery_file):
                with open(self.recovery_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.recovery_strategies = data.get("strategies", [])
        except Exception as e:
            print(f"Failed to load recovery strategies: {e}")
            self.recovery_strategies = []
    
    def save_data(self):
        """Save failure history and recovery strategies to files."""
        try:
            os.makedirs(os.path.dirname(self.failure_file), exist_ok=True)
            
            # Save failure history
            with open(self.failure_file, 'w', encoding='utf-8') as f:
                json.dump({
                    "failures": self.failures[-200:],  # Keep only recent 200
                    "last_updated": datetime.now().isoformat()
                }, f, indent=2, ensure_ascii=False)
            
            # Save recovery strategies
            with open(self.recovery_file, 'w', encoding='utf-8') as f:
                json.dump({
                    "strategies": self.recovery_strategies,
                    "last_updated": datetime.now().isoformat()
                }, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Failed to save failure data: {e}")
    
    def record_failure(self, action: Dict, error: str, context: Optional[Dict] = None) -> str:
        """
        Record a failed action.
        
        Args:
            action: The action that failed (dict with type, parameters, etc.)
            error: Error message
            context: Optional context (window info, user input, etc.)
        
        Returns:
            Failure ID for tracking
        """
        failure_id = f"fail_{int(time.time())}_{len(self.failures)}"
        
        failure = {
            "id": failure_id,
            "timestamp": datetime.now().isoformat(),
            "action": action,
            "error": error,
            "context": context or {},
            "recovered": False,
            "recovery_attempts": []
        }
        
        self.failures.append(failure)
        self.save_data()
        
        # Try to learn from similar past failures
        self._analyze_failure_pattern(failure)
        
        return failure_id
    
    def record_recovery_attempt(self, failure_id: str, recovery_action: Dict, success: bool):
        """
        Record an attempted recovery strategy.
        
        Args:
            failure_id: ID of the failure being recovered
            recovery_action: The recovery action attempted
            success: Whether the recovery was successful
        """
        for failure in self.failures:
            if failure["id"] == failure_id:
                failure["recovery_attempts"].append({
                    "timestamp": datetime.now().isoformat(),
                    "action": recovery_action,
                    "success": success
                })
                
                if success:
                    failure["recovered"] = True
                    self._learn_recovery_strategy(failure, recovery_action)
                
                self.save_data()
                break
    
    def _analyze_failure_pattern(self, failure: Dict):
        """Analyze a failure to identify patterns and suggest recovery."""
        action_type = failure.get("action", {}).get("type")
        error = failure.get("error", "").lower()
        
        # Find similar past failures
        similar_failures = [
            f for f in self.failures 
            if f.get("action", {}).get("type") == action_type
            and f.get("id") != failure.get("id")
            and f.get("recovered") == True
        ]
        
        # If we've recovered from similar failures, extract the pattern
        if similar_failures:
            for sf in similar_failures:
                successful_recoveries = [
                    ra for ra in sf.get("recovery_attempts", [])
                    if ra.get("success") == True
                ]
                
                if successful_recoveries:
                    # This is a known recoverable pattern
                    return True
        
        return False
    
    def _learn_recovery_strategy(self, failure: Dict, recovery_action: Dict):
        """Learn a new recovery strategy from a successful recovery."""
        action_type = failure.get("action", {}).get("type")
        error_pattern = self._extract_error_pattern(failure.get("error", ""))
        
        # Check if we already have this strategy
        for strategy in self.recovery_strategies:
            if (strategy.get("action_type") == action_type and
                strategy.get("error_pattern") == error_pattern):
                # Update existing strategy
                strategy["success_count"] = strategy.get("success_count", 0) + 1
                strategy["last_used"] = datetime.now().isoformat()
                strategy["recovery_action"] = recovery_action
                self.save_data()
                return
        
        # Add new strategy
        new_strategy = {
            "action_type": action_type,
            "error_pattern": error_pattern,
            "recovery_action": recovery_action,
            "success_count": 1,
            "created": datetime.now().isoformat(),
            "last_used": datetime.now().isoformat()
        }
        
        self.recovery_strategies.append(new_strategy)
        self.save_data()
    
    def suggest_recovery(self, action: Dict, error: str) -> Optional[Dict]:
        """
        Suggest a recovery action based on learned strategies.
        
        Args:
            action: The failed action
            error: The error message
        
        Returns:
            Suggested recovery action or None
        """
        action_type = action.get("type")
        error_pattern = self._extract_error_pattern(error)
        
        # Find matching strategies
        matching_strategies = [
            s for s in self.recovery_strategies
            if s.get("action_type") == action_type
            and s.get("error_pattern") == error_pattern
        ]
        
        if not matching_strategies:
            # Try generic fallback strategies
            return self._generic_recovery_strategy(action, error)
        
        # Return the most successful strategy
        best_strategy = max(matching_strategies, key=lambda s: s.get("success_count", 0))
        return best_strategy.get("recovery_action")
    
    def _extract_error_pattern(self, error: str) -> str:
        """Extract a pattern from an error message."""
        error_lower = error.lower()
        
        patterns = {
            "timeout": ["timeout", "timed out", "time limit exceeded"],
            "not_found": ["not found", "could not find", "no element", "no match"],
            "access_denied": ["access denied", "permission", "unauthorized"],
            "connection": ["connection", "network", "unreachable"],
            "invalid_input": ["invalid", "malformed", "incorrect format"],
        }
        
        for pattern_name, keywords in patterns.items():
            if any(keyword in error_lower for keyword in keywords):
                return pattern_name
        
        return "unknown"
    
    def _generic_recovery_strategy(self, action: Dict, error: str) -> Optional[Dict]:
        """Provide generic recovery strategies for common errors."""
        error_pattern = self._extract_error_pattern(error)
        action_type = action.get("type")
        
        generic_strategies = {
            "timeout": {
                "strategy": "increase_timeout",
                "action": {**action, "timeout_sec": action.get("timeout_sec", 30) * 2}
            },
            "not_found": {
                "strategy": "retry_with_wait",
                "action": {
                    "type": "wait_for_page_load",
                    "timeout_sec": 5,
                    "then": action
                }
            },
            "connection": {
                "strategy": "retry_after_delay",
                "delay_sec": 3,
                "action": action
            }
        }
        
        return generic_strategies.get(error_pattern, {}).get("action")
    
    def get_failure_stats(self) -> Dict:
        """Get statistics about failures and recoveries."""
        total_failures = len(self.failures)
        recovered_failures = sum(1 for f in self.failures if f.get("recovered"))
        
        # Count failures by type
        failure_by_type = {}
        for failure in self.failures:
            action_type = failure.get("action", {}).get("type", "unknown")
            failure_by_type[action_type] = failure_by_type.get(action_type, 0) + 1
        
        # Count recoveries by pattern
        recovery_by_pattern = {}
        for strategy in self.recovery_strategies:
            pattern = strategy.get("error_pattern", "unknown")
            count = strategy.get("success_count", 0)
            recovery_by_pattern[pattern] = recovery_by_pattern.get(pattern, 0) + count
        
        return {
            "total_failures": total_failures,
            "recovered_failures": recovered_failures,
            "recovery_rate": round(recovered_failures / total_failures * 100, 1) if total_failures > 0 else 0,
            "failure_by_type": failure_by_type,
            "recovery_by_pattern": recovery_by_pattern,
            "total_strategies": len(self.recovery_strategies)
        }
    
    def get_recent_failures(self, limit: int = 10) -> List[Dict]:
        """Get recent failures for display."""
        return self.failures[-limit:][::-1]  # Most recent first
    
    def clear_failures(self):
        """Clear all failure history."""
        self.failures = []
        self.save_data()


# Global instance
_failure_system = None


def get_failure_system() -> FailureLearningSystem:
    """Get the global failure learning system instance."""
    global _failure_system
    if _failure_system is None:
        _failure_system = FailureLearningSystem()
    return _failure_system
