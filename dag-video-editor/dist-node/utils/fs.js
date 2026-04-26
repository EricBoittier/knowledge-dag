"use strict";
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
exports.readJsonFile = readJsonFile;
exports.writeJsonFile = writeJsonFile;
exports.resolveFromRepoRoot = resolveFromRepoRoot;
const node_fs_1 = __importDefault(require("node:fs"));
const node_path_1 = __importDefault(require("node:path"));
function readJsonFile(p) {
    const text = node_fs_1.default.readFileSync(p, "utf8");
    return JSON.parse(text);
}
function writeJsonFile(p, payload) {
    node_fs_1.default.mkdirSync(node_path_1.default.dirname(p), { recursive: true });
    node_fs_1.default.writeFileSync(p, JSON.stringify(payload, null, 2) + "\n", "utf8");
}
function resolveFromRepoRoot(root, maybeRelative) {
    if (node_path_1.default.isAbsolute(maybeRelative)) {
        return maybeRelative;
    }
    return node_path_1.default.resolve(root, maybeRelative);
}
