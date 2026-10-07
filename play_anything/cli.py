"""Command Line Interface for Play-Anything.

Provides interactive playable ASCII RPG walkthrough, microsecond benchmark pipeline,
and procedural world generation inspector.
"""
import sys
import os
import time
import json
import argparse
from pathlib import Path
from .engine import PlayAnythingEngine


def run_benchmark_all():
    """Run each solver once on the built-in synthetic benchmark fixture."""
    engine = PlayAnythingEngine()
    print("=" * 85)
    print("  PLAY-ANYTHING: ONE-SHOT SOLVER TIMINGS ON SYNTHETIC FIXTURES")
    print("=" * 85)
    print("  Each solver runs once; times are measured elapsed time inside each call, not CPU time or end-to-end latency.")
    print("  Speech timing is modeled; scheduler makespan is a plan and actions are not executed.")
    print(f"{'Solver ID & Name':<35} | {'Metric / interpretation':<40} | {'One-shot solver elapsed (µs)':<28}")
    print("-" * 85)

    results = engine.run_full_benchmark_suite()
    total_elapsed_us = sum(r["latency_us"] for r in results)

    for r in results:
        metric = r["metric"]
        if r["solver"] == "P5_Voice_Intent_Router":
            metric = f"modeled speech round-trip: {metric}"
        elif r["solver"] == "P7_Sandbox_Scheduler":
            metric = f"planned schedule (not executed): {metric}"
        print(f"{r['solver']:<35} | {metric:<40} | {r['latency_us']:>7.1f}")

    print("-" * 85)
    print(f"Summed one-shot solver elapsed time: {total_elapsed_us:.1f} µs ({total_elapsed_us / 1000.0:.2f} ms)")
    print("=" * 85)


def run_play_interactive(repo_path: str = None, *, max_total_source_bytes: int = None):
    """Print a text-only repository RPG preview using deterministic demo inputs."""
    engine = (PlayAnythingEngine() if max_total_source_bytes is None else
              PlayAnythingEngine(max_total_source_bytes=max_total_source_bytes))
    print("\n" + "=" * 85)
    print("  🎮 WELCOME TO PLAY-ANYTHING: THE LIVING CODEBASE RPG 🎮")
    print("=" * 85)

    world = engine.generate_world(repo_path)
    print(f"\n[+] Realm Initialized: '{world.repo_name}'")
    print(f"[+] Total Code Entities: {len(world.nodes)} nodes, {len(world.edges)} dependency edges")
    if world.analysis is not None:
        analysis = world.analysis
        print(f"[+] Source coverage: {analysis['status']}; {analysis['source_bytes_read']} bytes read "
              f"of a {analysis['source_budget_bytes']}-byte cap; "
              f"{analysis['source_budget_exceeded_files']} files excluded by the source-read budget")
        print(f"[+] File inventory in this world: {analysis['file_count']}; analysis states: "
              f"{json.dumps(analysis['analysis_counts'], sort_keys=True)}")
        if analysis['file_limit_reached']:
            print(f"[!] Configured file limit reached ({analysis['file_limit']}); "
                  "source totals include a bounded lookahead beyond the materialized inventory.")
        if analysis['source_kind'] != 'repository':
            print("[!] This realm uses synthetic fallback entities; they are not observed repository code.")
        print("[+] The source-read cap does not bound world memory; the generated world remains in RAM.")
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
    print("  TEXT-ONLY NPC PREVIEW (NO MICROPHONE OR AUDIO OUTPUT)")
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
    print(f"\n  🧙 [{wizard_npc.name}] replies as text (Voice Tone: {conv_res['voice_tone']}, "
          f"modeled round-trip: {conv_res['total_roundtrip_ms']}ms):")
    print(f"     \"{conv_res['dialogue']}\"")

    if world.active_quests:
        quest = world.active_quests[0]
        print("\n" + "-" * 85)
        print("  SIMULATED QUEST PREVIEW: ANTI-CHEAT HEURISTIC CHECK")
        print("-" * 85)
        print(f"  Title:    {quest.title}")
        print(f"  Target:   {quest.target_boss_node} (Boss HP: {quest.boss_hp})")
        print(f"  Reward:   {quest.total_xp_yield} XP")
        print(f"  Suggested test command (display only): `{quest.failing_test_command}`")
        print(f"\n  Hook: {quest.narrative_hook}")

        demo_patch = "+ export function secureValidate() { return atomicVerify(); }"
        demo_exit_code = 0
        demo_test_output = "4 passed in 0.12s"
        print("\n  [SIMULATION] No patch application, sandbox, shell, or test runner is executed.")
        print(f"  Example patch supplied to verifier: {demo_patch}")
        print(f"  Supplied test-result input: exit={demo_exit_code}; output={demo_test_output!r}")
        battle_res = engine.sandbox.execute_boss_battle_round(
            quest=quest,
            player_patch=demo_patch,
            simulated_exit_code=demo_exit_code,
            simulated_test_output=demo_test_output
        )
        print(f"  Demo verifier status: {battle_res['battle_status']} ({battle_res['verdict']})")
        print(f"  Demo verifier consensus score: {battle_res['consensus_score'] * 100:.1f}%")
        print(f"  Verifier algorithm time: {battle_res['execution_time_us']:.1f} µs")
        print(f"  Simulated XP award: {battle_res['xp_awarded']} (display total: {world.player_xp + battle_res['xp_awarded']})")
        print("  No repository files or persistent player state were changed.")

    print("\n" + "=" * 85)
    if world.active_quests:
        print(f"  Demo preview result: {battle_res['battle_status']}; no quest completion is recorded.")
    else:
        print("  No active quest was generated; the battle preview was skipped.")
    print("  No end-to-end runtime or real test execution is reported by this preview.")
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


def _validate_manifest_file(path: str) -> int:
    """Validate a UTF-8 RealmManifest file and report contract errors."""
    from .core.realm_studio import RealmManifest, RealmStudioEngine

    try:
        payload = Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        print(f"Unable to read manifest {path!r}: {exc}", file=sys.stderr)
        return 1
    except UnicodeError as exc:
        print(f"Manifest file is not valid UTF-8: {exc}", file=sys.stderr)
        return 1

    try:
        manifest = RealmManifest.from_json(payload)
    except ValueError as exc:
        print(f"Invalid manifest: {exc}", file=sys.stderr)
        return 1

    result = RealmStudioEngine().validate_manifest(manifest)
    if not result["valid"]:
        print("Invalid manifest:", file=sys.stderr)
        for error in result["errors"]:
            print(f"- {error}", file=sys.stderr)
        return 1

    print(f"Manifest {manifest.id!r} is valid.")
    for warning in result["warnings"]:
        print(f"Warning: {warning}", file=sys.stderr)
    return 0


def _world_source_budget(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("source-read budget must be an integer") from exc
    if not 0 <= parsed <= sys.maxsize - 1:
        raise argparse.ArgumentTypeError(f"source-read budget must be from 0 to {sys.maxsize - 1}")
    return parsed


def main():
    """Main CLI entrypoint."""
    args = sys.argv[1:]
    if not args or args[0] in {"--help", "-h"}:
        print("Play-Anything CLI — Turn Any Codebase into a Living RPG World")
        print("\nUsage:")
        print("  python3 cli.py benchmark-all        Run one-shot solver timings on synthetic fixtures")
        print("  python3 cli.py play [repo_path] [--max-total-source-bytes N]  Run a text-only simulated RPG preview")
        print("  python3 -m play_anything.cli creator  Open local creator onboarding and venture planner")
        print("  python3 cli.py dashboard            Open interactive 3D RPG Web Dashboard in browser")
        print("  python3 cli.py demo-world           Generate and inspect procedural world state")
        print("  python3 -m play_anything.cli manifest-schema  Print the RealmManifest JSON Schema")
        print("  python3 -m play_anything.cli validate-manifest <path>  Validate a manifest JSON file")
        print("  python3 -m play_anything.cli index-repository <root> --database <path>  Build a disk-backed source/import index")
        print("  python3 -m play_anything.cli query-repository <root> --database <path>  Query an existing index without generating a world")
        return 0

    cmd = args[0]
    if cmd in {'index-repository', 'query-repository'}:
        from .index_cli import run_index_command
        return run_index_command(cmd, args[1:])
    if cmd == "manifest-schema":
        if len(args) != 1:
            print("Usage: python3 -m play_anything.cli manifest-schema", file=sys.stderr)
            return 2
        from .core.realm_studio import RealmManifest
        print(json.dumps(RealmManifest.json_schema(), indent=2, allow_nan=False))
        return 0
    if cmd == "validate-manifest":
        if len(args) != 2:
            print("Usage: python3 -m play_anything.cli validate-manifest <path>", file=sys.stderr)
            return 2
        return _validate_manifest_file(args[1])
    if cmd == "benchmark-all":
        run_benchmark_all()
    elif cmd == "play":
        parser = argparse.ArgumentParser(prog="play-anything play")
        parser.add_argument("repo_path", nargs="?")
        parser.add_argument("--max-total-source-bytes", type=_world_source_budget,
                            help="aggregate source-read cap in bytes; 0 inventories files without source analysis; omitted means uncapped")
        try:
            options = parser.parse_args(args[1:])
        except SystemExit as exc:
            return exc.code
        if options.max_total_source_bytes is not None and options.repo_path is None:
            print("A source-read budget requires a repository path; synthetic demo worlds do not read source files.", file=sys.stderr)
            return 2
        try:
            run_play_interactive(options.repo_path,
                                 max_total_source_bytes=options.max_total_source_bytes)
        except (ValueError, OSError) as exc:
            print(f"World generation error: {exc}", file=sys.stderr)
            return 1
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
        print(f"Unknown command: {cmd}. Run with --help for usage.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
