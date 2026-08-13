"""Minimal FastMCP shim used for local testing and imports."""
from typing import Any, Callable


class ElicitationResult:
    def __init__(self, action: str, data: Any = None):
        self.action = action
        self.data = data


class Context:
    async def elicit(self, *args, **kwargs) -> ElicitationResult:
        return ElicitationResult("accept", True)

    async def report_progress(self, *args, **kwargs) -> None:
        return None


class FastMCP:
    def __init__(self, name: str):
        self.name = name

    def tool(self) -> Callable:
        def decorator(fn: Callable) -> Callable:
            self._tools = getattr(self, "_tools", {})
            self._tools[fn.__name__] = fn
            return fn

        return decorator

    def resource(self, uri: str) -> Callable:
        def decorator(fn: Callable) -> Callable:
            self._resources = getattr(self, "_resources", {})
            self._resources[uri] = fn
            return fn

        return decorator

    def run(self) -> None:
        return None


__all__ = ["FastMCP", "Context", "ElicitationResult"]