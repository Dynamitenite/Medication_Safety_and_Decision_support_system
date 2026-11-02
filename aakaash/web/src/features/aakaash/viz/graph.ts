// Layout of the interaction graph. Pure logic: nodes on a circle, one edge per finding.
export type Level = "Medium" | "High" | "Critical";

export type GraphMedicine = { key: string; name: string; role: "new" | "current" };
export type GraphPair = { a: string; b: string; level: Level | null };
export type GraphAllergy = { medicineKey: string; allergyId: number; allergen: string; level: Level };
export type GraphInput = { medicines: GraphMedicine[]; pairs: GraphPair[]; allergies: GraphAllergy[] };

export type GraphNode = { id: string; label: string; kind: "new" | "current" | "allergen"; x: number; y: number };
export type GraphEdge = { id: string; from: string; to: string; level: Level | null; kind: "pair" | "allergy"; targetId: string; label: string; lx: number; ly: number };
export type GraphLayout =
  | { mode: "circular"; nodes: GraphNode[]; edges: GraphEdge[]; size: number }
  | { mode: "list-only"; reason: string; nodeCount: number };

export const MAX_NODES = 12;
export const GRAPH_SIZE = 360; // view box side; the circle is centred

/** Id of the finding card an edge points to. Keys are cleaned so the id is a valid fragment. */
export const findingId = (...parts: (string | number)[]) => "finding-" + parts.join("-").replace(/[^A-Za-z0-9_-]+/g, "_");

export function layoutGraph(input: GraphInput, size = GRAPH_SIZE): GraphLayout {
  const ordered = [...input.medicines].sort((x, y) => (x.role === y.role ? 0 : x.role === "new" ? -1 : 1));
  const keys = new Set(ordered.map((m) => m.key));
  const allergens = new Map<number, string>();
  for (const f of input.allergies) if (keys.has(f.medicineKey)) allergens.set(f.allergyId, f.allergen);
  const count = ordered.length + allergens.size;
  if (count > MAX_NODES) {
    return { mode: "list-only", nodeCount: count, reason: `The graph is drawn for up to ${MAX_NODES} items; this check has ${count}. The list below has every finding.` };
  }
  const ids = [
    ...ordered.map((m) => ({ id: m.key, label: m.name, kind: m.role })),
    ...[...allergens].map(([id, name]) => ({ id: `allergy:${id}`, label: name, kind: "allergen" as const })),
  ];
  const c = size / 2;
  const r = size * 0.34;
  const nodes: GraphNode[] = ids.map((n, i) => {
    const a = -Math.PI / 2 + (2 * Math.PI * i) / Math.max(ids.length, 1);
    return { ...n, x: c + r * Math.cos(a), y: c + r * Math.sin(a) };
  });
  const at = new Map(nodes.map((n) => [n.id, n]));
  const raw: Omit<GraphEdge, "lx" | "ly">[] = [];
  for (const p of input.pairs) {
    if (at.has(p.a) && at.has(p.b)) raw.push({ id: `e-${p.a}|${p.b}`, from: p.a, to: p.b, level: p.level, kind: "pair", targetId: findingId("p", p.a, p.b), label: p.level ?? "No level" });
  }
  for (const f of input.allergies) {
    if (at.has(f.medicineKey)) raw.push({ id: `e-${f.medicineKey}|allergy:${f.allergyId}`, from: f.medicineKey, to: `allergy:${f.allergyId}`, level: f.level, kind: "allergy", targetId: findingId("a", f.allergyId, f.medicineKey), label: f.level });
  }
  // labels sit at different points along their edge so edges through the middle do not stack their labels
  const along = [0.5, 0.36, 0.64];
  const edges: GraphEdge[] = raw.map((e, i) => {
    const p = at.get(e.from)!;
    const q = at.get(e.to)!;
    const t = along[i % along.length];
    return { ...e, lx: p.x + (q.x - p.x) * t, ly: p.y + (q.y - p.y) * t };
  });
  return { mode: "circular", nodes, edges, size };
}
