"""Formal allocation algorithms, Agent tools and feedback policy boundary."""
from copy import deepcopy
from typing import Protocol
from .agent import MessagesPolicy, run_agent
from .allocate import allocate
from .repair import interpret_feedback, repair


class AllocationPolicy(Protocol):
    def propose(self, model, system_spec, meter, out, history): ...
    def receive_feedback(self, candidate, feedback): ...


class AllocationStrategyPolicy:
    def __init__(self, strategy, config, seed=23):
        if strategy not in ('nominal', 'analytical', 'sensitivity_optimization', 'random', 'llm_agent'):
            raise ValueError('unsupported allocation strategy')
        self.strategy, self.config, self.seed = strategy, deepcopy(config), seed

    def propose(self, model, system_spec, meter, out, history):
        if history:
            if self.strategy == 'llm_agent':
                return None, {'status': 'REAL_LLM_REPAIR_NOT_IMPLEMENTED',
                              'reason': 'Existing real LLM interface is first-shot; feedback received for diagnosis.'}
            previous = history[-1]
            return repair(model, system_spec, previous['candidate'], previous['feedback'], meter)
        if self.strategy == 'llm_agent':
            policy = MessagesPolicy(self.config, out/'llm_calls', meter)
            return run_agent(deepcopy(model), deepcopy(system_spec), meter, out, policy)
        return allocate(self.strategy, deepcopy(model), deepcopy(system_spec), meter, self.seed)

    def receive_feedback(self, candidate, feedback):
        # Real call into the existing Agent layer, not merely a serialized callback placeholder.
        interpreted = interpret_feedback(candidate, feedback)
        return {'status': 'RECEIVED_BY_ALLOCATION_AGENT', 'interpretation': interpreted,
                'strategy': self.strategy, 'automatic_learning': False}


# Public Stage3A API compatibility; implementation and dependencies live here.
TrackAPolicy = AllocationStrategyPolicy
