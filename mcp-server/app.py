try:
    from .fastmcp import FastMCP
except Exception:
    # Fallback for direct execution / older layouts
    from fastmcp import FastMCP

# Import the newly created memory manager
from memory.memory_manager import MemoryManager

mcp = FastMCP("Spare Parts Inventory Management System")

# Initialize the global memory manager instance
# Note: We will keep llm_client=None until we wire the actual LLM
memory_manager = MemoryManager(llm_client=None)
