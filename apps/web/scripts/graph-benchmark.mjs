import Graph from "graphology";
import forceAtlas2 from "graphology-layout-forceatlas2";

const nodeCount = Number(process.argv[2] ?? 1800);
const iterations = Number(process.argv[3] ?? 30);
if (!Number.isInteger(nodeCount) || nodeCount < 2 || nodeCount > 10000) {
  throw new Error("nodeCount must be an integer from 2 to 10000");
}
if (!Number.isInteger(iterations) || iterations < 1 || iterations > 500) {
  throw new Error("iterations must be an integer from 1 to 500");
}

const graph = new Graph({ multi: true, type: "directed" });
const buildStart = performance.now();
for (let id = 0; id < nodeCount; id += 1) {
  graph.addNode(`node-${id}`, {
    x: Math.sin(id * 12.9898) * 5,
    y: Math.cos(id * 78.233) * 5,
    size: 4,
  });
}

let edgeCount = 0;
for (let source = 0; source < nodeCount; source += 1) {
  for (let offset = 1; offset <= 8; offset += 1) {
    const target = (source * 97 + offset * 31 + 17) % nodeCount;
    graph.addDirectedEdgeWithKey(`edge-${edgeCount}`, `node-${source}`, `node-${target}`, { weight: 1 });
    edgeCount += 1;
  }
}
const buildMs = performance.now() - buildStart;

const layoutStart = performance.now();
forceAtlas2.assign(graph, {
  iterations,
  settings: {
    gravity: 0.12,
    scalingRatio: 6,
    slowDown: 2,
    barnesHutOptimize: nodeCount > 200,
    outboundAttractionDistribution: true,
  },
});
const layoutMs = performance.now() - layoutStart;

let checksum = 0;
for (const node of graph.nodes()) {
  const { x, y } = graph.getNodeAttributes(node);
  checksum += x * 31 + y * 17;
}

console.log(JSON.stringify({
  nodes: graph.order,
  edges: edgeCount,
  iterations,
  buildMs: Number(buildMs.toFixed(2)),
  layoutMs: Number(layoutMs.toFixed(2)),
  checksum: Number(checksum.toFixed(4)),
  scope: "Graphology construction and synchronous ForceAtlas2 only; browser rendering is not measured",
}, null, 2));
