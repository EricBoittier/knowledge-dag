import fs from "node:fs";
import path from "node:path";

export function readJsonFile<T>(p: string): T {
  const text = fs.readFileSync(p, "utf8");
  return JSON.parse(text) as T;
}

export function writeJsonFile(p: string, payload: unknown): void {
  fs.mkdirSync(path.dirname(p), { recursive: true });
  fs.writeFileSync(p, JSON.stringify(payload, null, 2) + "\n", "utf8");
}

export function resolveFromRepoRoot(root: string, maybeRelative: string): string {
  if (path.isAbsolute(maybeRelative)) {
    return maybeRelative;
  }
  return path.resolve(root, maybeRelative);
}
