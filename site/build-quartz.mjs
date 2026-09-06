import { spawnSync } from "node:child_process";
import { existsSync, lstatSync, readdirSync } from "node:fs";
import { dirname, join, parse, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const mediaSuffixes = new Set([
  ".aac",
  ".avi",
  ".avif",
  ".bmp",
  ".flac",
  ".gif",
  ".jpeg",
  ".jpg",
  ".m4a",
  ".mkv",
  ".mov",
  ".mp3",
  ".mp4",
  ".ogg",
  ".png",
  ".svgz",
  ".tiff",
  ".wav",
  ".webm",
  ".webp",
]);

function inspectTree(root) {
  for (const entry of readdirSync(root, { withFileTypes: true })) {
    const path = join(root, entry.name);
    if (entry.isSymbolicLink())
      throw new Error(`wiki symlink is forbidden: ${path}`);
    if (entry.isDirectory()) inspectTree(path);
    if (entry.isFile()) {
      const suffix = entry.name.includes(".")
        ? `.${entry.name.split(".").at(-1).toLowerCase()}`
        : "";
      if (mediaSuffixes.has(suffix))
        throw new Error(`retained source media is forbidden: ${path}`);
    }
  }
}

const siteRoot = dirname(fileURLToPath(import.meta.url));
const repositoryRoot = resolve(siteRoot, "..");
const wikiPath = resolve(
  process.env.WIKI_PATH || join(repositoryRoot, "data", "wiki"),
);
const outputPath = resolve(
  process.env.ROBOTELIER_SITE_OUTPUT || join(siteRoot, "public"),
);
const bootstrap = join(siteRoot, "quartz", "bootstrap-cli.mjs");

if (
  !existsSync(wikiPath) ||
  !lstatSync(wikiPath).isDirectory() ||
  lstatSync(wikiPath).isSymbolicLink()
) {
  throw new Error(`WIKI_PATH must be a regular directory: ${wikiPath}`);
}
if (!existsSync(bootstrap) || !lstatSync(bootstrap).isFile()) {
  throw new Error(
    "pinned Quartz engine is unavailable; run prepare-engine first",
  );
}
if (
  outputPath === parse(outputPath).root ||
  outputPath === repositoryRoot ||
  outputPath === siteRoot ||
  outputPath === wikiPath ||
  outputPath.startsWith(`${wikiPath}/`)
) {
  throw new Error(`refusing unsafe Quartz output path: ${outputPath}`);
}

inspectTree(wikiPath);
const result = spawnSync(
  process.execPath,
  [bootstrap, "build", "-d", wikiPath, "-o", outputPath, "--concurrency=1"],
  { cwd: siteRoot, env: process.env, stdio: "inherit" },
);
if (result.error) throw result.error;
if (result.status !== 0) process.exitCode = result.status ?? 1;
