"""
Play-Anything: Adaptive Personalization & Behavioral Calibration Engine
Surpasses Meta's Muse AI via multi-dimensional behavioral monitoring, generational age clustering,
and zero-shot expertise calibration.

CORE MANDATE:
- Kids & Youth (8-15): Simplified, visually intuitive metaphors, foundational algorithmic growth, positive scaffolding.
- Middle-Aged Professionals (25-55): Fast-track zero-handholding, skips juvenile basics, high-density telemetry, max time efficiency.
- Seniors & Elders (60+): High-contrast ergonomic UI, relaxed timers, cognitive vitality & mental longevity preservation.
All dynamically calibrated in the first 30 seconds of realm onboarding.
"""

from __future__ import annotations
import uuid
import time
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field, asdict
from enum import Enum


class AgeCluster(str, Enum):
    YOUTH_CADET = "youth_cadet_8_15"          # Kids / young teens: Visual metaphors, gamified growth
    PRO_ARCHITECT = "pro_architect_25_55"      # Working professionals: Zero fluff, instant deep-dive
    SENIOR_SAGE = "senior_sage_60_plus"        # Elders: High readability, cognitive vitality, paced
    ADAPTIVE_AUTO = "adaptive_auto_detect"     # Real-time behavioral inference via latency & syntax


class ExpertiseTier(str, Enum):
    INITIATE = "initiate"                      # Basic variables & loops
    PRACTITIONER = "practitioner"              # Functional programming & modular design
    STAFF_ARCHITECT = "staff_architect"        # Distributed consensus, memory safety, concurrency
    GRANDMASTER_APEX = "grandmaster_apex"      # Zero-day exploitation, compiler internals, micro-optimizations


@dataclass
class BehavioralTelemetry:
    """Real-time micro-behavioral signals captured during the first 30s onboarding interaction."""
    keystroke_cadence_cpm: float = 280.0       # Characters per minute
    hesitation_interval_ms: float = 120.0      # Pause before complex AST node interaction
    error_recovery_latency_ms: float = 450.0   # Speed of self-correcting syntax errors
    terminal_command_density: float = 0.85     # Ratio of CLI/hotkey usage vs GUI clicks
    cyclomatic_comprehension_score: float = 0.92  # Ability to parse nested branching logic


@dataclass
class PersonalizationProfile:
    user_id: str
    age_cluster: AgeCluster
    expertise_tier: ExpertiseTier
    skip_basic_tutorials: bool
    scaffolding_style: str                    # "visual_story_metaphor", "raw_ast_telemetry", "ergonomic_paced_scholar"
    ui_font_scale: float                      # 1.0 = standard, 1.25 = senior ergonomic, 1.1 = youth friendly
    high_contrast_mode: bool
    countdown_timer_multiplier: float         # 0.75 for fast pro speedruns, 1.5 for elders
    cognitive_load_limit: int                 # Concurrently displayed concepts (3 for kids, 12 for pros)
    created_at: float = field(default_factory=time.time)


@dataclass
class OnboardingCalibrationGate:
    """Map-level onboarding gateway defining how developers adapt their maps to player clusters."""
    map_id: str
    map_title: str
    supports_cadet_mode: bool = True
    supports_pro_fast_track: bool = True
    supports_senior_sage_mode: bool = True
    pro_bypass_qualification_test: str = "Instant 30s Mutex Race-Condition Triage"
    cadet_visual_metaphor: str = "The Enchanted Code Castle: Repairing the Magic Portcullis"
    senior_vitality_focus: str = "Cognitive Precision: Memory Alignment & Logical Pathways"


class AdaptivePersonalizationEngine:
    """
    Evaluates behavioral telemetry and personal identification signals to assign the optimal
    pedagogical and operational track for any player.
    """

    def calibrate_player_profile(
        self,
        user_id: str,
        stated_age: Optional[int] = None,
        telemetry: Optional[BehavioralTelemetry] = None
    ) -> PersonalizationProfile:
        telemetry = telemetry or BehavioralTelemetry()

        # 1. Determine Age Cluster
        if stated_age is not None:
            if stated_age <= 16:
                cluster = AgeCluster.YOUTH_CADET
            elif stated_age >= 60:
                cluster = AgeCluster.SENIOR_SAGE
            else:
                cluster = AgeCluster.PRO_ARCHITECT
        else:
            # Behavioral Inference
            if telemetry.terminal_command_density > 0.6 and telemetry.keystroke_cadence_cpm > 200:
                cluster = AgeCluster.PRO_ARCHITECT
            elif telemetry.hesitation_interval_ms > 400 and telemetry.terminal_command_density < 0.2:
                cluster = AgeCluster.SENIOR_SAGE
            else:
                cluster = AgeCluster.YOUTH_CADET

        # 2. Determine Expertise Tier & Scaffolding Style
        if cluster == AgeCluster.PRO_ARCHITECT:
            tier = ExpertiseTier.STAFF_ARCHITECT if telemetry.cyclomatic_comprehension_score > 0.8 else ExpertiseTier.PRACTITIONER
            skip_basics = True
            scaffolding = "raw_ast_telemetry"
            font_scale = 1.0
            high_contrast = False
            timer_mult = 0.85
            load_limit = 12
        elif cluster == AgeCluster.SENIOR_SAGE:
            tier = ExpertiseTier.PRACTITIONER
            skip_basics = False
            scaffolding = "ergonomic_paced_scholar"
            font_scale = 1.25
            high_contrast = True
            timer_mult = 1.60
            load_limit = 5
        else:  # YOUTH_CADET
            tier = ExpertiseTier.INITIATE
            skip_basics = False
            scaffolding = "visual_story_metaphor"
            font_scale = 1.10
            high_contrast = False
            timer_mult = 1.25
            load_limit = 4

        return PersonalizationProfile(
            user_id=user_id,
            age_cluster=cluster,
            expertise_tier=tier,
            skip_basic_tutorials=skip_basics,
            scaffolding_style=scaffolding,
            ui_font_scale=font_scale,
            high_contrast_mode=high_contrast,
            countdown_timer_multiplier=timer_mult,
            cognitive_load_limit=load_limit
        )

    def adapt_map_onboarding(
        self,
        gate: OnboardingCalibrationGate,
        profile: PersonalizationProfile
    ) -> Dict[str, Any]:
        """
        Generates the customized onboarding flow for the map according to the player profile.
        """
        if profile.age_cluster == AgeCluster.PRO_ARCHITECT:
            return {
                "track": "EXECUTIVE_PRO_FAST_TRACK",
                "onboarding_time_seconds": 15,
                "banner_title": f"⚡ Pro Architect Fast-Track Active: {gate.map_title}",
                "narrative": "Basic tutorials bypassed. Direct injection into Production AST with full compiler telemetry.",
                "actions": [
                    "Direct Git Diff Terminal Unlocked",
                    "Advanced Mutex Sandbox Active",
                    "Zero Handholding / Maximum Time Efficiency"
                ],
                "ui_adjustments": {
                    "font_scale": profile.ui_font_scale,
                    "high_contrast": profile.high_contrast_mode,
                    "displayed_nodes_max": profile.cognitive_load_limit
                }
            }
        elif profile.age_cluster == AgeCluster.SENIOR_SAGE:
            return {
                "track": "COGNITIVE_VITALITY_SAGE_TRACK",
                "onboarding_time_seconds": 90,
                "banner_title": f"🌿 Paced Cognitive Exploration: {gate.map_title}",
                "narrative": gate.senior_vitality_focus,
                "actions": [
                    "High-Contrast Ergonomic Visual Hierarchy",
                    "Paced Timer (+60% Reaction Window)",
                    "Memory & Pattern Retention Scaffolding"
                ],
                "ui_adjustments": {
                    "font_scale": profile.ui_font_scale,
                    "high_contrast": profile.high_contrast_mode,
                    "displayed_nodes_max": profile.cognitive_load_limit
                }
            }
        else:  # YOUTH_CADET
            return {
                "track": "YOUTH_CADET_DISCOVERY_TRACK",
                "onboarding_time_seconds": 60,
                "banner_title": f"🚀 Cadet Adventure Academy: {gate.map_title}",
                "narrative": gate.cadet_visual_metaphor,
                "actions": [
                    "Story-Driven Visual Block Scaffolding",
                    "Friendly NPC Guide Companion",
                    "Step-by-Step Interactive Quest Milestones"
                ],
                "ui_adjustments": {
                    "font_scale": profile.ui_font_scale,
                    "high_contrast": profile.high_contrast_mode,
                    "displayed_nodes_max": profile.cognitive_load_limit
                }
            }
