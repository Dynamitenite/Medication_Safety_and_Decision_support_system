// Layout of the interaction graph. Pure logic: nodes on a circle, one edge per finding.
export type Level = "Medium" | "High" | "Critical";

export type GraphMedicine = { key: string; name: string; role: "new" | "current" };
export type GraphPair = { a: string; b: string; level: Level | null };
export type GraphAllergy = { medicineKey: string; allergyId: number; allergen: string; level: Level };
export type GraphInput = { medicines: GraphMedicine[]; pairs: GraphPair[]; allergies: GraphAllergy[] };

export type GraphNode = {
  id: string;
  label: string;
  kind: "new" | "current" | "allergen";
  x: number;
  y: number;
  /** the name wrapped to the room beside the node, ending in "…" when it was cut; the full name stays in `label` */
  lines: string[];
  /** where the first line is drawn and how it hangs from there */
  tx: number;
  ty: number;
  anchor: "start" | "middle" | "end";
};
export type GraphEdge = { id: string; from: string; to: string; level: Level | null; kind: "pair" | "allergy"; targetId: string; label: string; lx: number; ly: number };
export type GraphLayout =
  | { mode: "circular"; nodes: GraphNode[]; edges: GraphEdge[]; size: number }
  | { mode: "list-only"; reason: string; nodeCount: number };

export const MAX_NODES = 12;
export const GRAPH_SIZE = 360; // view box side; the circle is centred
/** average glyph width at the 11 px label size, and the line step of a wrapped name */
export const GLYPH_PX = 6.2;
export const LINE_PX = 13;
const MAX_LINES = 3;

/** Width of the pill that carries a finding's level next to its line. */
export const pillWidth = (label: string) => Math.round(label.length * 6.4 + 28);
export const PILL_H = 22;

/** Breaks a name at spaces into lines of at most `maxChars`; what does not fit in `maxLines` is cut with "…". */
export function wrapLabel(name: string, maxChars: number, maxLines = MAX_LINES): string[] {
  const n = Math.max(maxChars, 4);
  const lines: string[] = [];
  let cur = "";
  const words = name.trim().split(/\s+/).filter(Boolean);
  for (let w of words) {
    while (w.length > n) {
      // a single word longer than a line: split it
      if (cur) {
        lines.push(cur);
        cur = "";
      }
      lines.push(w.slice(0, n));
      w = w.slice(n);
    }
    if (!cur) cur = w;
    else if (cur.length + 1 + w.length <= n) cur += " " + w;
    else {
      lines.push(cur);
      cur = w;
    }
  }
  if (cur) lines.push(cur);
  if (lines.length <= maxLines) return lines.length ? lines : [""];
  const kept = lines.slice(0, maxLines);
  const last = kept[maxLines - 1];
  kept[maxLines - 1] = (last.length >= n ? last.slice(0, n - 1) : last) + "…";
  return kept;
}

/** Id of the finding card an edge points to. Keys are cleaned so the id is a valid fragment. */
export const findingId = (...parts: (string | number)[]) => "finding-" + parts.join("-").replace(/[^A-Za-z0-9_-]+/g, "_");

/** `size` is the side of the square the circle sits in (px at 1:1); `radius` defaults to a third of it. A
 *  smaller radius leaves more room at the sides for the names. */
export function layoutGraph(input: GraphInput, size = GRAPH_SIZE, radius = size * 0.34): GraphLayout {
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
  const r = radius;
  const nodes: GraphNode[] = ids.map((n, i) => {
    const a = -Math.PI / 2 + (2 * Math.PI * i) / Math.max(ids.length, 1);
    const x = c + r * Math.cos(a);
    const y = c + r * Math.sin(a);
    // the name goes straight out from the circle, inside the room left on that side
    const ux = Math.cos(a);
    const uy = Math.sin(a);
    const bx = x + ux * 16;
    const by = y + uy * 16;
    const anchor = Math.abs(ux) < 0.3 ? "middle" : ux > 0 ? "start" : "end";
    const room = anchor === "middle" ? 2 * Math.min(bx, size - bx) - 4 : anchor === "start" ? size - bx - 2 : bx - 2;
    const lines = wrapLabel(n.label, Math.floor(room / GLYPH_PX));
    const ty = uy < -0.5 ? by - 3 - (lines.length - 1) * LINE_PX : uy > 0.5 ? by + 11 : by + 4 - ((lines.length - 1) * LINE_PX) / 2;
    return { ...n, x, y, lines, tx: bx, ty, anchor };
  });
  const at = new Map(nodes.map((n) => [n.id, n]));
  const raw: Omit<GraphEdge, "lx" | "ly">[] = [];
  for (const p of input.pairs) {
    if (at.has(p.a) && at.has(p.b)) raw.push({ id: `e-${p.a}|${p.b}`, from: p.a, to: p.b, level: p.level, kind: "pair", targetId: findingId("p", p.a, p.b), label: p.level ?? "No level" });
  }
  for (const f of input.allergies) {
    if (at.has(f.medicineKey)) raw.push({ id: `e-${f.medicineKey}|allergy:${f.allergyId}`, from: f.medicineKey, to: `allergy:${f.allergyId}`, level: f.level, kind: "allergy", targetId: findingId("a", f.allergyId, f.medicineKey), label: f.level });
  }
  // each level label takes the first place along its edge where it covers no other label and no node
  const along = [0.5, 0.4, 0.6, 0.32, 0.68, 0.25, 0.75, 0.18, 0.82];
  const sideways = [0, 13, -13, 26, -26]; // px off the line, when the line itself has no free place
  type Box = { x: number; y: number; w: number; h: number; weight: number };
  const placed: Box[] = nodes.flatMap((n) => {
    const w = Math.max(...n.lines.map((l) => l.length)) * GLYPH_PX;
    const h = n.lines.length * LINE_PX;
    const cx = n.anchor === "middle" ? n.tx : n.anchor === "start" ? n.tx + w / 2 : n.tx - w / 2;
    return [{ x: n.x, y: n.y, w: 24, h: 24, weight: 1 }, { x: cx, y: n.ty + ((n.lines.length - 1) * LINE_PX) / 2 - 4, w, h, weight: 1 }];
  });
  const hit = (a: { x: number; y: number; w: number; h: number }, b: Box) =>
    Math.abs(a.x - b.x) < (a.w + b.w) / 2 && Math.abs(a.y - b.y) < (a.h + b.h) / 2;
  const edges: GraphEdge[] = raw.map((e) => {
    const p = at.get(e.from)!;
    const q = at.get(e.to)!;
    const w = pillWidth(e.label);
    const len = Math.hypot(q.x - p.x, q.y - p.y) || 1;
    const nx = -(q.y - p.y) / len;
    const ny = (q.x - p.x) / len;
    let best = { lx: p.x + (q.x - p.x) * 0.5, ly: p.y + (q.y - p.y) * 0.5, clash: Infinity };
    search: for (const off of sideways) {
      for (const t of along) {
        const lx = p.x + (q.x - p.x) * t + nx * off;
        const ly = p.y + (q.y - p.y) * t + ny * off;
        // covering another level label counts for more than touching a node or a name
        const clash = placed.reduce((sum, b) => sum + (hit({ x: lx, y: ly, w, h: PILL_H }, b) ? b.weight : 0), 0);
        if (clash < best.clash) best = { lx, ly, clash };
        if (clash === 0) break search;
      }
    }
    placed.push({ x: best.lx, y: best.ly, w, h: PILL_H, weight: 10 });
    return { ...e, lx: best.lx, ly: best.ly };
  });
  return { mode: "circular", nodes, edges, size };
}
