import { PipelineConfig } from "../config";
import { readJsonFile } from "../utils/fs";
import { DagNode, DagSnapshot } from "../types";

export class DagAdapter {
  private readonly snapshot: DagSnapshot;

  constructor(private readonly config: PipelineConfig) {
    this.snapshot = readJsonFile<DagSnapshot>(this.config.dag.snapshot_path);
  }

  getRootConcepts(): DagNode[] {
    const incoming = new Set(this.snapshot.edges.map((e) => e.to));
    const roots = this.snapshot.nodes.filter((n) => !incoming.has(n.id));
    return this.sortByImportance(roots);
  }

  getConceptChildren(conceptId: string): DagNode[] {
    const toIds = this.snapshot.edges.filter((e) => e.from === conceptId).map((e) => e.to);
    const childSet = new Set(toIds);
    const children = this.snapshot.nodes.filter((n) => childSet.has(n.id));
    return this.sortByImportance(children);
  }

  getConceptMetadata(conceptId: string): DagNode | undefined {
    return this.snapshot.nodes.find((n) => n.id === conceptId);
  }

  listNarrativeOrder(maxSegments: number): DagNode[] {
    const ordered: DagNode[] = [];
    const seen = new Set<string>();
    const visit = (node: DagNode) => {
      if (seen.has(node.id) || ordered.length >= maxSegments) {
        return;
      }
      seen.add(node.id);
      ordered.push(node);
      for (const child of this.getConceptChildren(node.id)) {
        visit(child);
      }
    };

    for (const root of this.getRootConcepts()) {
      visit(root);
    }
    return ordered.slice(0, maxSegments);
  }

  private sortByImportance(nodes: DagNode[]): DagNode[] {
    return [...nodes].sort((a, b) => (b.importance ?? 0) - (a.importance ?? 0) || a.title.localeCompare(b.title));
  }
}
