"""
mcp-server/rag/__init__.py

The modules in this package (chunking.py, embeddings.py, vector_store.py,
etc.) import each other with bare names -- `from chunking import Chunk`,
not `from rag.chunking import Chunk` -- so they can also be run directly
as scripts (`python3 rag/naive_rag.py`) for quick manual testing, which is
how they were developed and demoed.

For that to also work when server.py does `from rag import
search_knowledge_tool`, this package's own directory needs to be on
sys.path so those bare imports resolve. Doing it here means callers of
the package don't need to know or care about this detail.
"""

import sys
from pathlib import Path

_THIS_DIR = str(Path(__file__).resolve().parent)
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)
