"""
Play-Anything: Realm Studio & Creator Economy Engine (Fortnite / Roblox for Developers)
Allows any engineer or creator to design, configure, benchmark, publish, and monetize
custom codebase maps/realms with customized controls, objectives, rewards, and punishments.
"""

from __future__ import annotations
import json
import uuid
import time
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field, asdict
from enum import Enum


class GameMode(str, Enum):
    BOSS_RAID = "boss_raid"
    CAPTURE_THE_FLAG = "capture_the_flag"
    SPEEDRUN_REFACTOR = "speedrun_refactor"
    TOWER_DEFENSE = "tower_defense"
    CODE_GOLF = "code_golf"
    BATTLE_ROYALE = "battle_royale"
    ONBOARDING_WALKTHROUGH = "onboarding_walkthrough"


class ControlScheme(str, Enum):
    ISOMETRIC_POINT_CLICK = "isometric_point_click"
    WASD_SPATIAL_EXPLORER = "wasd_spatial_explorer"
    VIM_MODAL_NAVIGATION = "vim_modal_navigation"
    VOICE_COMMANDED_SWARM = "voice_commanded_swarm"
    GAMEPAD_TWIN_STICK = "gamepad_twin_stick"


class SandboxTier(str, Enum):
    WASM_MICRO_ISOLATE = "wasm_micro_isolate"      # Sub-millisecond startup, memory bound
    DOCKER_CONTAINER = "docker_container"          # Full filesystem, network isolation
    FIRECRACKER_MICROVM = "firecracker_microvm"    # Hardware-virtualized zero-trust security


class AntiCheatStrictness(str, Enum):
    RELAXED = "relaxed"              # Basic exit-code check
    STRICT = "strict"                # Exit code + Mock detection + AST delta check
    SOVEREIGN_PARANOID = "paranoid"  # Exit code + AST validation + Prompt injection quarantine + Kemeny consensus trap


class AccessType(str, Enum):
    FREE_TO_PLAY = "free_to_play"
    PREMIUM_TICKET = "premium_ticket"
    SUBSCRIPTION_PASS = "subscription_pass"
    SPONSORED_ENTERPRISE_BOUNTY = "sponsored_enterprise_bounty"


@dataclass
class RealmRequirement:
    target_language: str
    min_runtime_version: str
    sandbox_tier: SandboxTier = SandboxTier.DOCKER_CONTAINER
    max_memory_mb: int = 512
    max_cpu_time_ms: int = 3000
    allowed_dependencies: List[str] = field(default_factory=list)
    min_hero_level: int = 1
    min_player_elo: int = 1000


@dataclass
class RealmControlsConfig:
    primary_scheme: ControlScheme = ControlScheme.ISOMETRIC_POINT_CLICK
    allow_voice_commands: bool = True
    keybindings: Dict[str, str] = field(default_factory=lambda: {
        "inspect_node": "E",
        "run_tests": "R",
        "open_skill_tree": "K",
        "voice_ptt": "Space",
        "quick_diff": "Tab"
    })
    voice_prompts_map: Dict[str, str] = field(default_factory=lambda: {
        "scan chamber": "DISPEL_FOG",
        "attack boss": "TRIGGER_TEST_RUNNER",
        "request mentor": "SUMMON_ARCHMAGE"
    })


@dataclass
class RealmObjective:
    id: str
    title: str
    description: str
    target_metric: str        # e.g., "test_passed", "coverage_pct", "cyclomatic_max", "latency_us"
    target_threshold: float   # e.g., 100.0, 95.0, 5.0, 200.0
    xp_reward: int
    gold_reward: int
    is_mandatory: bool = True


@dataclass
class RealmBenchmarkGuardrails:
    max_pipeline_latency_us: float = 1000.0  # Must solve in < 1ms
    min_mutation_score_pct: float = 90.0     # Tests must kill >= 90% mutants
    max_cyclomatic_complexity: int = 8       # No monster spaghetti functions
    max_memory_rss_mb: int = 256
    anti_cheat_mode: AntiCheatStrictness = AntiCheatStrictness.STRICT


@dataclass
class RealmPunishments:
    slashing_penalty_pct: float = 15.0       # Stake slashed on cheat attempt
    elo_penalty: int = 40                    # ELO drop on failed raid
    tech_debt_debuff: str = "Tangled Dependencies: +25% Mana cost on subsequent actions"
    cursed_blame_artifact: str = "Cursed Mock Wrapper of False Passing"


@dataclass
class RealmMonetizationConfig:
    access_type: AccessType = AccessType.FREE_TO_PLAY
    ticket_price_tokens: int = 0             # 0 for F2P, e.g. 50 GitCoins
    creator_rev_share_pct: float = 70.0      # 70% to creator, 30% platform
    engagement_pool_eligible: bool = True    # Receives slice of 40% subscription engagement pool
    custom_skins_allowed: bool = True
    sponsored_bounty_usd: float = 0.0        # Sponsored corporate prize pool


@dataclass
class RealmManifest:
    id: str
    title: str
    slug: str
    author: str
    version: str
    description: str
    game_mode: GameMode
    repository_url: str
    requirements: RealmRequirement
    controls: RealmControlsConfig
    objectives: List[RealmObjective]
    benchmarks: RealmBenchmarkGuardrails
    punishments: RealmPunishments
    monetization: RealmMonetizationConfig
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> RealmManifest:
        data = data.copy()
        data["game_mode"] = GameMode(data["game_mode"])
        data["requirements"]["sandbox_tier"] = SandboxTier(data["requirements"]["sandbox_tier"])
        data["requirements"] = RealmRequirement(**data["requirements"])
        data["controls"]["primary_scheme"] = ControlScheme(data["controls"]["primary_scheme"])
        data["controls"] = RealmControlsConfig(**data["controls"])
        data["objectives"] = [RealmObjective(**obj) for obj in data["objectives"]]
        data["benchmarks"]["anti_cheat_mode"] = AntiCheatStrictness(data["benchmarks"]["anti_cheat_mode"])
        data["benchmarks"] = RealmBenchmarkGuardrails(**data["benchmarks"])
        data["punishments"] = RealmPunishments(**data["punishments"])
        data["monetization"]["access_type"] = AccessType(data["monetization"]["access_type"])
        data["monetization"] = RealmMonetizationConfig(**data["monetization"])
        return cls(**data)


class RealmStudioEngine:
    """
    Studio Engine for compiling, validating, and publishing custom developer realms.
    Enforces provable balance, anti-cheat validation, and monetization accounting.
    """

    def __init__(self):
        self.published_realms: Dict[str, RealmManifest] = {}

    def create_template_manifest(
        self,
        title: str,
        author: str,
        repository_url: str,
        game_mode: GameMode = GameMode.BOSS_RAID
    ) -> RealmManifest:
        realm_id = f"realm_{uuid.uuid4().hex[:8]}"
        slug = title.lower().replace(" ", "-").replace(".", "_")

        objectives = [
            RealmObjective(
                id="obj_01",
                title="Quell the Race Condition Golem",
                description="Refactor the asynchronous order mutex to prevent double-spending.",
                target_metric="test_passed",
                target_threshold=100.0,
                xp_reward=1450,
                gold_reward=150,
                is_mandatory=True
            ),
            RealmObjective(
                id="obj_02",
                title="Attain Flawless Coverage",
                description="Achieve >= 95% statement and branch coverage in OrderProcessor.",
                target_metric="coverage_pct",
                target_threshold=95.0,
                xp_reward=600,
                gold_reward=75,
                is_mandatory=False
            )
        ]

        manifest = RealmManifest(
            id=realm_id,
            title=title,
            slug=slug,
            author=author,
            version="1.0.0",
            description=f"Playable codebase realm for {title}, engineered for {game_mode.value}.",
            game_mode=game_mode,
            repository_url=repository_url,
            requirements=RealmRequirement(
                target_language="TypeScript / Node.js 20+",
                min_runtime_version="20.0.0",
                sandbox_tier=SandboxTier.DOCKER_CONTAINER,
                max_memory_mb=512,
                max_cpu_time_ms=2500
            ),
            controls=RealmControlsConfig(),
            objectives=objectives,
            benchmarks=RealmBenchmarkGuardrails(),
            punishments=RealmPunishments(),
            monetization=RealmMonetizationConfig()
        )
        return manifest

    def validate_manifest(self, manifest: RealmManifest) -> Dict[str, Any]:
        """Validates manifest against system invariants and fairness standards."""
        errors = []
        warnings = []

        if not manifest.title or len(manifest.title) < 3:
            errors.append("Title must be at least 3 characters.")

        if not manifest.objectives or len(manifest.objectives) == 0:
            errors.append("At least one objective must be declared.")

        mandatory_count = sum(1 for o in manifest.objectives if o.is_mandatory)
        if mandatory_count == 0:
            errors.append("At least one mandatory objective is required for victory conditions.")

        if manifest.benchmarks.max_pipeline_latency_us > 50000.0:
            warnings.append("Pipeline latency benchmark exceeds 50ms; may cause client frame stutter.")

        if manifest.monetization.creator_rev_share_pct > 85.0:
            errors.append("Creator revenue share cannot exceed 85.0% (Platform minimum margin 15%).")

        is_valid = len(errors) == 0
        return {
            "valid": is_valid,
            "errors": errors,
            "warnings": warnings,
            "manifest_id": manifest.id
        }

    def publish_realm(self, manifest: RealmManifest) -> Dict[str, Any]:
        val = self.validate_manifest(manifest)
        if not val["valid"]:
            raise ValueError(f"Manifest validation failed: {val['errors']}")

        self.published_realms[manifest.id] = manifest
        return {
            "status": "PUBLISHED",
            "realm_id": manifest.id,
            "slug": manifest.slug,
            "share_url": f"playanything://realms/{manifest.slug}",
            "creator_rev_share": f"{manifest.monetization.creator_rev_share_pct}%"
        }

    def simulate_payout_distribution(
        self,
        realm_id: str,
        total_plays: int,
        completion_rate: float,
        ticket_sales_revenue_tokens: int,
        engagement_pool_size_tokens: int
    ) -> Dict[str, Any]:
        """
        Calculates creator earnings based on Roblox DevEx + Fortnite Engagement Pool model.
        """
        if realm_id not in self.published_realms:
            raise KeyError(f"Realm {realm_id} not registered.")

        manifest = self.published_realms[realm_id]
        rev_share_ratio = manifest.monetization.creator_rev_share_pct / 100.0

        # 1. Direct Ticket & Microtransaction Sales (e.g. 70%)
        direct_creator_cut = int(ticket_sales_revenue_tokens * rev_share_ratio)
        direct_platform_cut = ticket_sales_revenue_tokens - direct_creator_cut

        # 2. Engagement Payout Pool (Fortnite 2.0 Island Engagement Model)
        # Weighted by total plays and retention/completion rate
        engagement_score = total_plays * (0.4 + 0.6 * completion_rate)
        # Simulated proportional share of pool
        pool_share_factor = min(1.0, engagement_score / 10000.0)
        engagement_payout_tokens = int(engagement_pool_size_tokens * 0.15 * pool_share_factor)

        total_creator_tokens = direct_creator_cut + engagement_payout_tokens
        # Exchange rate: 100 GitCoins / Mana = $1.00 USD (Roblox DevEx standard)
        devex_usd_equivalent = round(total_creator_tokens * 0.01, 2)

        return {
            "realm_id": realm_id,
            "realm_title": manifest.title,
            "total_plays": total_plays,
            "completion_rate": completion_rate,
            "direct_creator_tokens": direct_creator_cut,
            "engagement_pool_tokens": engagement_payout_tokens,
            "total_creator_tokens": total_creator_tokens,
            "platform_fee_tokens": direct_platform_cut,
            "estimated_devex_usd": devex_usd_equivalent
        }
