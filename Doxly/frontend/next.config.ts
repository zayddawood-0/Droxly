import path from "node:path";
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Pins the workspace root to this directory so Turbopack doesn't walk up
  // into the user's home directory looking for a lockfile (a stray, unrelated
  // package-lock.json can otherwise exist above the repo on a given machine).
  turbopack: {
    root: path.join(__dirname),
  },
  // Produces a minimal, self-contained server bundle (only the production
  // deps actually reachable at runtime) — what the Dockerfile's runtime
  // stage copies, per skills/devops.md's "keep the image lean" guidance.
  output: "standalone",
};

export default nextConfig;
