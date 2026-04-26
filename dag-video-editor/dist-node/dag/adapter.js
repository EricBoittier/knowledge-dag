"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.DagAdapter = void 0;
const fs_1 = require("../utils/fs");
class DagAdapter {
    constructor(config) {
        this.config = config;
        this.snapshot = (0, fs_1.readJsonFile)(this.config.dag.snapshot_path);
    }
    getRootConcepts() {
        const incoming = new Set(this.snapshot.edges.map((e) => e.to));
        const roots = this.snapshot.nodes.filter((n) => !incoming.has(n.id));
        return this.sortByImportance(roots);
    }
    getConceptChildren(conceptId) {
        const toIds = this.snapshot.edges.filter((e) => e.from === conceptId).map((e) => e.to);
        const childSet = new Set(toIds);
        const children = this.snapshot.nodes.filter((n) => childSet.has(n.id));
        return this.sortByImportance(children);
    }
    getConceptMetadata(conceptId) {
        return this.snapshot.nodes.find((n) => n.id === conceptId);
    }
    listNarrativeOrder(maxSegments) {
        const ordered = [];
        const seen = new Set();
        const visit = (node) => {
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
    sortByImportance(nodes) {
        return [...nodes].sort((a, b) => (b.importance ?? 0) - (a.importance ?? 0) || a.title.localeCompare(b.title));
    }
}
exports.DagAdapter = DagAdapter;
