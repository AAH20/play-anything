"""Command Line Interface for Play-Anything.

Provides interactive playable ASCII RPG walkthrough, microsecond benchmark pipeline,
and procedural world generation inspector.
"""
import sys
import os
import time
from .engine import PlayAnythingEngine


def run_benchmark_all():
    """Executes microsecond benchmark suite across all 10 solvers."""
    engine = PlayAnythingEngine()
    print("=" * 85)
    print("  PLAY-ANYTHING: 10 APEX COMBINATORIAL GRAPH & SWARM SOLVERS BENCHMARK")
    print("=" * 85)
    print(f"{'Solver ID & Name':<35} | {'Key Metric':<25} | {'Latency':<12}")
    print("-" * 85)

    results = engine.run_full_benchmark_suite()
    total_latency_us = sum(r["latency_us"] for r in results)

    for r in results:
        print(f"{r['solver']:<35} | {r['metric']:<25} | {r['latency_us']:>7.1f} µs")

    print("-" * 85)
    print(f"Total Combined Pipeline Benchmark Execution: {total_latency_us:.1f} µs ({total_latency_us / 1000.0:.2f} ms)")
    print("=" * 85)


def run_play_interactive(repo_path: str = None):
    """Launches an interactive ASCII RPG exploration of the repository."""
    engine = PlayAnythingEngine()
    print("\n" + "=" * 85)
    print("  🎮 WELCOME TO PLAY-ANYTHING: THE LIVING CODEBASE RPG 🎮")
    print("=" * 85)

    world = engine.generate_world(repo_path)
    print(f"\n[+] Realm Initialized: '{world.repo_name}'")
    print(f"[+] Total Code Entities: {len(world.nodes)} nodes, {len(world.edges)} dependency edges")
    print(f"[+] Skill Tree Depth: {world.skill_tree.tree_depth} tiers ({len(world.skill_tree.skill_nodes)} unlockable skills)")
    print(f"[+] Dungeon Partition: {world.dungeon.partition_count} chambers ({world.dungeon.cut_edges_count} inter-room cuts)")

    print("\n" + "-" * 85)
    print("  HERO CHARACTER SHEET")
    print("-" * 85)
    print(f"  Class: Staff Architect Sorcerer       Level: {world.player_level}")
    print(f"  XP:    {world.player_xp} / 500                       Mana:  {world.player_mana} / 1000")
    print(f"  Active Dungeon Chambers:")
    for r in world.dungeon.rooms:
        status = "⚔️ [UNLOCKED]" if not r.is_fog_covered else "🌫️ [FOG OF WAR]"
        boss_label = f" (Boss: {r.boss_node_id})" if r.boss_node_id else ""
        print(f"    • {r.room_id}: {r.name:<45} {status}{boss_label}")

    print("\n" + "-" * 85)
    print("  LIVING NPC ENCOUNTER (Full-Duplex Voice Swarm)")
    print("-" * 85)
    wizard_npc = next((p for p in world.personas if p.archetype == "Senior Architect Wizard"), world.personas[0])
    print(f"  You approach [{wizard_npc.name}] ({wizard_npc.archetype})...")
    print(f"  You ask: 'Great Wizard, what is the architectural invariant of this realm?'")

    conv_res = engine.voice.converse_with_npc(
        persona=wizard_npc,
        user_speech_text="architectural invariant of this realm",
        codebase_nodes=world.nodes,
        codebase_edges=world.edges
    )
    print(f"\n  🧙 [{wizard_npc.name}] speaks (Voice Tone: {conv_res['voice_tone']}, Latency: {conv_res['total_roundtrip_ms']}ms):")
    print(f"     \"{conv_res['dialogue']}\"")

    if world.active_quests:
        quest = world.active_quests[0]
        print("\n" + "-" * 85)
        print("  ACTIVE RAID QUEST: COMPUTER-USE BOSS BATTLE")
        print("-" * 85)
        print(f"  Title:    {quest.title}")
        print(f"  Target:   {quest.target_boss_node} (Boss HP: {quest.boss_hp})")
        print(f"  Reward:   {quest.total_xp_yield} XP")
        print(f"  Failing:  `{quest.failing_test_command}`")
        print(f"\n  Hook: {quest.narrative_hook}")

        print("\n  [Action] Dispatching Computer-Use Sandbox to apply patch and run test runner...")
        battle_res = engine.sandbox.execute_boss_battle_round(
            quest=quest,
            player_patch="+ export function secureValidate() { return atomicVerify(); }",
            simulated_exit_code=0,
            simulated_test_output="4 passed in 0.12s"
        )
        print(f"  {battle_res['combat_log']}")
        print(f"  Anti-Cheat Consensus: {battle_res['consensus_score'] * 100:.1f}% Verified Authentic ({battle_res['execution_time_us']:.1f} µs)")
        print(f"  New Player XP: {world.player_xp + battle_res['xp_awarded']} -> LEVEL UP! (Level 2 Architect)")

    print("\n" + "=" * 85)
    print("  QUEST COMPLETE! Real-world code transformed into living play in < 1 millisecond.")
    print("=" * 85 + "\n")


def open_dashboard():
    """Opens the interactive 3D Codebase RPG World in the user's browser."""
    import webbrowser
    dashboard_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dashboard.html")
    if os.path.exists(dashboard_path):
        uri = "file://" + os.path.abspath(dashboard_path)
        print(f"Launching Play-Anything Spatial RPG Dashboard: {uri}")
        webbrowser.open(uri)
    else:
        print(f"Dashboard file not found at: {dashboard_path}")


def main():
    """Main CLI entrypoint."""
    args = sys.argv[1:]
    if not args or args[0] in {"--help", "-h"}:
        print("Play-Anything CLI — Turn Any Codebase into a Living RPG World")
        print("\nUsage:")
        print("  python3 cli.py benchmark-all        Run microsecond benchmark suite across 10 solvers")
        print("  python3 cli.py play [repo_path]     Launch interactive playable terminal RPG")
        print("  python3 -m play_anything.cli creator  Open local creator onboarding and venture planner")
        print("  python3 cli.py dashboard            Open interactive 3D RPG Web Dashboard in browser")
        print("  python3 cli.py demo-world           Generate and inspect procedural world state")
        sys.exit(0)

    cmd = args[0]
    if cmd == "benchmark-all":
        run_benchmark_all()
    elif cmd == "play":
        path = args[1] if len(args) > 1 else None
        run_play_interactive(path)
    elif cmd == "creator":
        from play_anything.creator_server import main as creator_main
        sys.argv = [sys.argv[0], *args[1:]]
        creator_main()
    elif cmd == "dashboard":
        open_dashboard()
    elif cmd == "demo-world":
        engine = PlayAnythingEngine()
        world = engine.generate_world()
        print(f"Successfully generated world for: {world.repo_name}")
        print(f"Rooms: {len(world.dungeon.rooms)}, Skills: {len(world.skill_tree.skill_nodes)}, NPCs: {len(world.personas)}")
    else:
        print(f"Unknown command: {cmd}. Run with --help for usage.")
        sys.exit(1)


if __name__ == "__main__":
    main()
