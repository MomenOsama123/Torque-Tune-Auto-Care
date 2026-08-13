from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime

@dataclass
class Message:
    """
    Data representing a single message within the short-term memory.
    """
    role: str  # Expected values: 'user', 'assistant', 'tool_call', 'tool_output'
    content: Any
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: Optional[Dict[str, Any]] = None  # Useful for storing tool names or elicitation states

class ShortTermMemory:
    """
    Short-term memory that retains the context of the current conversation.
    """
    def __init__(self, max_capacity: int = 10):
        # max_capacity is the maximum number of messages before the system decides to drop or promote to Episodic Memory
        self.max_capacity = max_capacity
        self.messages: List[Message] = []

    def add_message(self, role: str, content: Any, metadata: Optional[Dict[str, Any]] = None) -> None:
        """Add a new message to the memory."""
        msg = Message(role=role, content=content, metadata=metadata)
        self.messages.append(msg)

    def get_context(self) -> List[Dict[str, Any]]:
        """Return the conversation context as a list of dictionaries for the LLM."""
        return [
            {
                "role": msg.role,
                "content": msg.content,
                "metadata": msg.metadata,
                "time": msg.timestamp.isoformat()
            }
            for msg in self.messages
        ]

    def is_full(self) -> bool:
        """Check if the short-term memory is full and needs flushing (to trigger the Router)."""
        return len(self.messages) >= self.max_capacity
        
    def clear(self) -> List[Message]:
        """Clear the memory and return the old messages in case the Router needs them."""
        old_messages = self.messages.copy()
        self.messages.clear()
        return old_messages