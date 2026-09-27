"""Full-Duplex Voice Agent Adapter for Codebase Living NPCs.

Handles streaming voice dialogue with autonomous codebase NPCs (Wizards, Rogues, Blacksmiths, Clerics).
Integrates real-time speech-to-intent routing with sub-180ms roundtrip deadlines.
"""
import time
from typing import List, Dict, Optional, Tuple, Any
from ..core.models import VoicePacket, LatencyConstrainedVoiceResult, AgentPersona, CodeNode, CodeEdge
from ..core.voice_intent_router import solve_voice_intent_routing


class VoiceAgentAdapter:
    """Manages low-latency voice interactions with codebase-resident NPCs."""

    @staticmethod
    def converse_with_npc(
        persona: AgentPersona,
        user_speech_text: str,
        codebase_nodes: List[CodeNode],
        codebase_edges: List[CodeEdge],
        deadline_ms: float = 180.0
    ) -> Dict[str, Any]:
        """Executes full-duplex speech-to-intent routing and generates in-character NPC dialogue."""
        # Extract keywords
        words = user_speech_text.lower().replace("?", "").replace(".", "").split()
        keywords = [w for w in words if len(w) > 3]

        packet = VoicePacket(
            packet_id=f"voice_{persona.npc_id}_{int(time.time()*1000) if 'time' in globals() else 100}",
            user_transcript=user_speech_text,
            extracted_entities=keywords,
            deadline_ms=deadline_ms
        )

        route_res = solve_voice_intent_routing(
            packet=packet,
            nodes=codebase_nodes,
            edges=codebase_edges
        )

        # Generate persona-grounded dialogue based on archetype
        referenced_node_names = [n.name for n in codebase_nodes if n.node_id in route_res.selected_subgraph]
        ref_text = ", ".join(referenced_node_names[:2]) if referenced_node_names else "the ancient scrolls"

        if persona.archetype == "Senior Architect Wizard":
            dialogue = (
                f"Observe closely, seeker. The data flows through {ref_text}. "
                f"If you violate the state invariants here, the entire castle will crumble!"
            )
        elif persona.archetype == "Security Rogue":
            dialogue = (
                f"Heh, you left a blind spot in {ref_text}. "
                f"A clever infiltrator could bypass authentication before you even notice."
            )
        elif persona.archetype == "DevOps Blacksmith":
            dialogue = (
                f"By the sparks of the CI forge! The builds around {ref_text} are burning too much fuel. "
                f"Time to hammer down those dependencies!"
            )
        else:
            dialogue = f"Greetings! I stand guardian over {ref_text}. What is your quest?"

        return {
            "speaker_name": persona.name,
            "archetype": persona.archetype,
            "dialogue": dialogue,
            "voice_tone": persona.voice_tone,
            "referenced_nodes": route_res.selected_subgraph,
            "total_roundtrip_ms": route_res.total_roundtrip_ms,
            "latency_deadline_met": route_res.deadline_met,
            "execution_time_us": route_res.execution_time_us
        }
