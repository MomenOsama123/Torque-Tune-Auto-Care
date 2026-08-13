import os

# Shim package to expose the existing `mcp-server` directory as `mcp`.
_shim_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'mcp-server'))
if os.path.isdir(_shim_path):
    __path__.insert(0, _shim_path)

__all__ = []
