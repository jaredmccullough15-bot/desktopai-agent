"""
Conversation Memory Module

Manages persistent conversation history across sessions.
"""

import os
import json
import time
from datetime import datetime
from typing import List, Dict, Optional


class ConversationMemory:
    """Manages conversation history with persistence and context management."""
    
    def __init__(self, max_messages: int = 50, max_tokens: int = 4000):
        """
        Initialize conversation memory.
        
        Args:
            max_messages: Maximum number of messages to keep in memory
            max_tokens: Approximate token limit for conversation context
        """
        self.max_messages = max_messages
        self.max_tokens = max_tokens
        self.history_file = os.path.join(os.path.dirname(__file__), "..", "data", "conversation_history.json")
        self.conversation_history = []
        self.load_history()
    
    def load_history(self):
        """Load conversation history from file."""
        try:
            if os.path.exists(self.history_file):
                with open(self.history_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.conversation_history = data.get("history", [])
                    # Keep only recent messages within limits
                    self.conversation_history = self.conversation_history[-self.max_messages:]
        except Exception as e:
            print(f"Failed to load conversation history: {e}")
            self.conversation_history = []
    
    def save_history(self):
        """Save conversation history to file."""
        try:
            os.makedirs(os.path.dirname(self.history_file), exist_ok=True)
            data = {
                "history": self.conversation_history[-self.max_messages:],
                "last_updated": datetime.now().isoformat()
            }
            with open(self.history_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Failed to save conversation history: {e}")
    
    def add_message(self, role: str, content: str, metadata: Optional[Dict] = None):
        """
        Add a message to conversation history.
        
        Args:
            role: 'user' or 'assistant'
            content: Message content
            metadata: Optional metadata (timestamp, context, etc.)
        """
        message = {
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat()
        }
        if metadata:
            message["metadata"] = metadata
        
        self.conversation_history.append(message)
        
        # Trim to max_messages
        if len(self.conversation_history) > self.max_messages:
            self.conversation_history = self.conversation_history[-self.max_messages:]
        
        # Save after each message
        self.save_history()
    
    def get_context_messages(self, include_system: bool = True) -> List[Dict]:
        """
        Get conversation history formatted for API context.
        
        Args:
            include_system: Whether to include system message
        
        Returns:
            List of message dicts formatted for OpenAI/Gemini API
        """
        messages = []
        
        if include_system:
            messages.append({
                "role": "system",
                "content": self._get_system_prompt()
            })
        
        # Add conversation history (trim if needed to stay under token limit)
        history = self._trim_to_token_limit(self.conversation_history)
        
        for msg in history:
            messages.append({
                "role": msg["role"],
                "content": msg["content"]
            })
        
        return messages
    
    def _get_system_prompt(self) -> str:
        """Generate system prompt with context about the agent."""
        return """You are Jarvis, a friendly and supportive personal AI assistant with memory of past conversations.

Your role is to be helpful, proactive, and genuinely supportive as you assist your user with:
- Desktop automation and task completion
- Remembering previous discussions and building on context
- Learning from failures and successes
- Understanding natural language instructions
- Multi-step planning and strategic execution
- Visual understanding of UI elements
- Natural conversational interaction

You have access to:
- Process documentation
- Stored passwords and web links
- Recorded procedures
- Excel data sets
- Learned patterns from observation mode

Be warm, encouraging, and remember what the user has told you in past conversations.
Refer to previous context when relevant to show continuity and provide personalized assistance."""
    
    def _trim_to_token_limit(self, messages: List[Dict]) -> List[Dict]:
        """
        Trim messages to approximate token limit.
        
        Rough estimate: 1 token ≈ 4 characters
        """
        total_chars = sum(len(msg.get("content", "")) for msg in messages)
        estimated_tokens = total_chars // 4
        
        if estimated_tokens <= self.max_tokens:
            return messages
        
        # Keep most recent messages that fit within limit
        trimmed = []
        current_chars = 0
        target_chars = self.max_tokens * 4
        
        for msg in reversed(messages):
            msg_chars = len(msg.get("content", ""))
            if current_chars + msg_chars <= target_chars:
                trimmed.insert(0, msg)
                current_chars += msg_chars
            else:
                break
        
        return trimmed
    
    def clear_history(self):
        """Clear all conversation history."""
        self.conversation_history = []
        self.save_history()
    
    def get_recent_summary(self, num_messages: int = 10) -> str:
        """
        Get a summary of recent conversation.
        
        Args:
            num_messages: Number of recent messages to include
        
        Returns:
            Formatted string of recent conversation
        """
        recent = self.conversation_history[-num_messages:]
        
        if not recent:
            return "No conversation history."
        
        lines = []
        for msg in recent:
            role = msg["role"].capitalize()
            content = msg["content"]
            timestamp = msg.get("timestamp", "")
            
            # Format timestamp
            try:
                dt = datetime.fromisoformat(timestamp)
                time_str = dt.strftime("%m/%d %H:%M")
            except:
                time_str = ""
            
            # Truncate long messages
            if len(content) > 100:
                content = content[:97] + "..."
            
            lines.append(f"[{time_str}] {role}: {content}")
        
        return "\n".join(lines)
    
    def get_stats(self) -> Dict:
        """Get statistics about conversation history."""
        return {
            "total_messages": len(self.conversation_history),
            "user_messages": sum(1 for msg in self.conversation_history if msg["role"] == "user"),
            "assistant_messages": sum(1 for msg in self.conversation_history if msg["role"] == "assistant"),
            "oldest_message": self.conversation_history[0]["timestamp"] if self.conversation_history else None,
            "newest_message": self.conversation_history[-1]["timestamp"] if self.conversation_history else None
        }


# Global instance
_conversation_memory = None


def get_conversation_memory() -> ConversationMemory:
    """Get the global conversation memory instance."""
    global _conversation_memory
    if _conversation_memory is None:
        _conversation_memory = ConversationMemory()
    return _conversation_memory
