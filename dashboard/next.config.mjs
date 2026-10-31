import { dirname } from "node:path";
import { fileURLToPath } from "node:url";

// Static export: `npm run build` writes a plain HTML/JS site to out/.
// Set BASE_PATH (e.g. "/carbon-paper") when hosting under a sub-path such as GitHub Pages.
const basePath = process.env.BASE_PATH || "";

/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "export",
  basePath,
  images: { unoptimized: true },
  trailingSlash: true,
  // The parent NusaCarbon app has its own lockfile; keep this project self-contained.
  turbopack: { root: dirname(fileURLToPath(import.meta.url)) },
};

export default nextConfig;
