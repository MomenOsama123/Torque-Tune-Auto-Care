from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field

@dataclass
class ScratchpadState:
    """
    Data structure to hold the current reasoning state of the agent.
    """
    current_goal: Optional[str] = None
    current_plan: List[str] = field(default_factory=list)
    completed_steps: List[str] = field(default_factory=list)
    next_action: Optional[str] = None
    intermediate_results: Dict[str, Any] = field(default_factory=dict)

class Scratchpad:
    """
    The Scratchpad is separate from the conversation history.
    It stores the agent's internal reasoning state to ensure execution continuity.
    """
    def __init__(self):
        self.state = ScratchpadState()

    def set_goal(self, goal: str, plan: List[str]) -> None:
        """
        Set a new main goal and the initial plan (steps) to achieve it.
        """
        self.state.current_goal = goal
        self.state.current_plan = plan
        self.state.completed_steps = []
        self.state.next_action = plan[0] if plan else None
        self.state.intermediate_results = {}

    def complete_step(self, step: str, result: Optional[Any] = None, result_key: Optional[str] = None) -> None:
        """
        Mark a step from the plan as completed and optionally save its result.
        """
        if step in self.state.current_plan:
            self.state.current_plan.remove(step)
        
        self.state.completed_steps.append(step)
        
        # Store intermediate result if provided (e.g., search output needed for a later update)
        if result_key and result is not None:
            self.state.intermediate_results[result_key] = result
            
        # Automatically set the next action to the upcoming step in the plan
        self.state.next_action = self.state.current_plan[0] if self.state.current_plan else None

    def update_next_action(self, action: str) -> None:
        """
        Manually override the next action if the plan changes dynamically.
        """
        self.state.next_action = action

    def get_state(self) -> Dict[str, Any]:
        """
        Retrieve the current reasoning state, usually to inject into the LLM prompt.
        """
        return {
            "current_goal": self.state.current_goal,
            "current_plan": self.state.current_plan,
            "completed_steps": self.state.completed_steps,
            "next_action": self.state.next_action,
            "intermediate_results": self.state.intermediate_results
        }

    def clear(self) -> None:
        """
        Clear the scratchpad once the main goal is fully achieved.
        """
        self.state = ScratchpadState()