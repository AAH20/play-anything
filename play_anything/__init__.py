"""Play-Anything: Turn Any Codebase into an Interactive Living RPG World.

The apex of agentic graph engineering, full-duplex voice swarms, and computer-use sandboxes.
"""
from .engine import PlayAnythingEngine
from .adapters.repo_rpg_generator import WorldState, RepoRPGGenerator
from .adapters.voice_agent_adapter import VoiceAgentAdapter
from .adapters.computer_use_sandbox_adapter import ComputerUseSandboxAdapter

__version__ = "1.0.0"
__all__ = [
    "PlayAnythingEngine",
    "WorldState",
    "RepoRPGGenerator",
    "VoiceAgentAdapter",
    "ComputerUseSandboxAdapter",
    "__version__",
]
