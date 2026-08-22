// `output: "standalone"` (next.config.ts) produces a self-contained server
// bundle but deliberately excludes public/ and .next/static — Next.js
// expects the deployer to copy them in (documented Next.js standalone
// convention). Run automatically after every build (package.json
// "postbuild") so `node .next/standalone/server.js` and the Dockerfile's
// runtime stage both work from one correct, consistent output.
import { cpSync, existsSync } from "node:fs";
import path from "node:path";

const root = process.cwd();
const copies = [
  [path.join(root, "public"), path.join(root, ".next/standalone/public")],
  [path.join(root, ".next/static"), path.join(root, ".next/standalone/.next/static")],
];

for (const [from, to] of copies) {
  if (!existsSync(from)) continue;
  cpSync(from, to, { recursive: true });
}
