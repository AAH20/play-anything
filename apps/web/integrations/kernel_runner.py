"""Fixed adapter to the four pinned, dependency-free AAH20 kernel APIs."""
import dataclasses
import enum
import json
import os
import sys
import time

PINS = {
    "graph-rag-kernel": ("graph_rag_np_hard_kernel", "35b1bb93a04d419fc1167480d93a1eed711fb711", "graph-rag-np-hard-kernel"),
    "agentic-kernel": ("agentic_np_hard_kernel", "ad8e99faa20c414b60d86b8ec211863c003535fc", "agentic-np-hard-kernel"),
    "mirofish-optimizer": ("mirofish_swarm_optimizer", "d2a3df25cf80750fadd562373f7941b9cb8db2f1", "mirofish-swarm-optimizer"),
    "graph-swarm-kernel": ("agentic_graph_swarm_kernel", "d429ee702e0e9b59b68f3714723a4f1d4bc425c8", "agentic-graph-swarm-kernel"),
}


def serialize(value):
    if dataclasses.is_dataclass(value):
        return {key: serialize(item) for key, item in dataclasses.asdict(value).items()}
    if isinstance(value, enum.Enum):
        return value.value
    if isinstance(value, dict):
        return {str(serialize(key)): serialize(item) for key, item in value.items()}
    if isinstance(value, (set, tuple, list)):
        return [serialize(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def verify_source(integration_id, root):
    package, revision, manifest_name = PINS[integration_id]
    if not os.path.isfile(os.path.join(root, package, "engine.py")):
        raise ValueError("configured kernel repository does not contain its pinned engine path")
    manifest_path = os.path.join(os.path.dirname(root), "sources.json")
    if not os.path.isfile(manifest_path):
        raise ValueError("missing pinned kernel source manifest next to configured repository")
    with open(manifest_path, encoding="utf-8") as source:
        manifest = json.load(source)
    entries = [item for item in manifest if item.get("name") == manifest_name and os.path.realpath(item.get("path", "")) == root]
    if not entries or entries[0].get("revision") != revision:
        raise ValueError("kernel source manifest does not match the reviewed revision")
    return revision


def result_for(integration_id, graph, params, root):
    revision = verify_source(integration_id, root)
    sys.path.insert(0, root)
    nodes, edges = graph["nodes"], graph["edges"]
    counts = {"nodesSelected": len(nodes), "nodesTotal": len(nodes), "edgesSelected": len(edges), "edgesTotal": len(edges), "omittedNodes": 0, "omittedEdges": 0}
    started = time.perf_counter()
    if integration_id == "graph-rag-kernel":
        from graph_rag_np_hard_kernel.engine import GraphRAGNPHardEngine
        ordered_nodes = sorted(node["id"] for node in nodes)
        ordered_edges = sorted((edge["source"], edge["target"], float(edge.get("count", 1))) for edge in edges)
        if any(not weight >= 0 or not __import__("math").isfinite(weight) for _, _, weight in ordered_edges):
            raise ValueError("community graph weights must be finite and nonnegative")
        result = GraphRAGNPHardEngine().detect_communities_modularity(ordered_nodes, ordered_edges, gamma=float(params.get("gamma", 1)))
    elif integration_id == "agentic-kernel":
        from agentic_np_hard_kernel.engine import AgenticNPHardEngine
        from agentic_np_hard_kernel.core.models import SubTask
        tasks = [SubTask(node["id"], node["name"][:300], 1.0, [], node["kind"]) for node in nodes]
        by_id = {node["id"]: task for node, task in zip(nodes, tasks)}
        for edge in edges:
            if edge["source"] != edge["target"]:
                target = by_id[edge["target"]]
                if edge["source"] not in target.dependencies:
                    target.dependencies.append(edge["source"])
        task_ids = {task.task_id for task in tasks}
        if any(dependency not in task_ids for task in tasks for dependency in task.dependencies):
            raise ValueError("workflow graph has a prerequisite outside the selected task set")
        successors = {task.task_id: [] for task in tasks}
        indegree = {task.task_id: 0 for task in tasks}
        for task in tasks:
            for dependency in task.dependencies:
                successors[dependency].append(task.task_id)
                indegree[task.task_id] += 1
        ready = [task_id for task_id, degree in indegree.items() if degree == 0]
        visited = 0
        while ready:
            current = ready.pop()
            visited += 1
            for target in successors[current]:
                indegree[target] -= 1
                if indegree[target] == 0:
                    ready.append(target)
        if visited != len(tasks):
            raise ValueError("workflow graph contains a cycle; upstream solver does not validate cyclic input")
        result = AgenticNPHardEngine().synthesize_workflow_dag(tasks)
    elif integration_id == "mirofish-optimizer":
        if not nodes:
            raise ValueError("influence analysis requires at least one graph node")
        from mirofish_swarm_optimizer.engine import MiroFishSwarmEngine
        from mirofish_swarm_optimizer.core.models import AgentFaction, SwarmAgent
        agents = [SwarmAgent(node["id"], node["name"][:300], AgentFaction.MEDIA_INFLUENCER, min(1.0, max(0.01, float(node.get("connections", 1) or 1))), [0.0], 100) for node in nodes]
        network = {node["id"]: [] for node in nodes}
        for edge in edges:
            network[edge["source"]].append((edge["target"], min(1.0, max(0.01, float(edge.get("count", 1))))))
            if edge["source"] != edge["target"]:
                network[edge["target"]].append((edge["source"], min(1.0, max(0.01, float(edge.get("count", 1))))))
        result = MiroFishSwarmEngine().solve_critical_influence(agents, network, k_seeds=min(int(params.get("kSeeds", 3)), len(nodes)))
    else:
        from agentic_graph_swarm_kernel.engine import AgenticGraphSwarmEngine
        from agentic_graph_swarm_kernel.core.models import AgentBeliefGraph, FactStatement
        statements = {}
        names = {node["id"]: node["name"][:300] for node in nodes}
        for edge in edges:
            statements.setdefault(edge["source"], []).append(FactStatement(names[edge["source"]], edge["relation"][:100], names[edge["target"]], 0.9 if edge["confidence"] in ("parsed", "observed") else 0.5))
        beliefs = [AgentBeliefGraph(node["id"], 1.0, statements.get(node["id"], [])) for node in nodes]
        result = AgenticGraphSwarmEngine.solve_consensus(beliefs)
    elapsed = (time.perf_counter() - started) * 1000
    serialized = serialize(result)
    claim = None
    if integration_id == "graph-swarm-kernel":
        # The upstream flag is unconditional and is not a cycle check. Recompute from returned facts.
        facts = serialized.get("consensus_graph", [])
        adjacency = {}
        for fact in facts:
            adjacency.setdefault(fact["subject"], []).append(fact["obj"])
        colors = {}
        def visit(subject):
            colors[subject] = 1
            for target in adjacency.get(subject, []):
                if target not in adjacency:
                    continue
                if colors.get(target) == 1 or colors.get(target, 0) == 0 and visit(target):
                    return True
            colors[subject] = 2
            return False
        has_cycle = any(colors.get(subject, 0) == 0 and visit(subject) for subject in adjacency)
        claim = {"upstreamCycleFreeClaim": serialized.pop("cycle_free_certified", None), "cycleFreeVerified": not has_cycle, "warning": "The upstream cycle_free_certified field is unconditional; cycleFreeVerified was independently computed over returned subject/object triples."}
    return {"integrationId": integration_id, "operation": {"graph-rag-kernel": "communities", "agentic-kernel": "workflow", "mirofish-optimizer": "influence", "graph-swarm-kernel": "consensus"}[integration_id], "sourceRevision": revision, "inputCounts": counts, "elapsedMs": round(elapsed, 3), "assumptions": {"graph-rag-kernel": ["Edge count is used as nonnegative traversal weight.", "Inputs are sorted for reproducibility; this is greedy local modularity, not a global optimum."], "agentic-kernel": ["Every task is modeled as one time unit.", "Edges are dependencies from source to target; cycles are rejected before invoking the upstream solver."], "mirofish-optimizer": ["All nodes are modeled as media influencers with influence derived from observed connection counts.", "Directed graph edges are symmetrized for influence propagation; this is the kernel's RR coverage objective."], "graph-swarm-kernel": ["Each graph node is a belief agent.", "Semantic graph edges become attributed statements; parsed/observed evidence receives 0.9 confidence, other evidence 0.5."]}[integration_id], "cycleAssessment": claim, "result": serialized}


def main():
    if len(sys.argv) != 3 or sys.argv[2] not in PINS:
        raise ValueError("invalid fixed kernel selection")
    root, integration_id = os.path.realpath(sys.argv[1]), sys.argv[2]
    request = json.load(sys.stdin)
    graph, params = request.get("graph"), request.get("parameters", {})
    if not isinstance(graph, dict) or not isinstance(params, dict):
        raise ValueError("invalid adapter input")
    if len(graph.get("nodes", [])) > 500 or len(graph.get("edges", [])) > 5000:
        raise ValueError("kernel input exceeds explicit limits")
    if not graph.get("nodes"):
        raise ValueError("kernel analysis requires at least one graph node")
    output = result_for(integration_id, graph, params, root)
    print(json.dumps(output, separators=(",", ":"), allow_nan=False))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"kernel runner: {type(error).__name__}: {error}", file=sys.stderr)
        raise SystemExit(1)
