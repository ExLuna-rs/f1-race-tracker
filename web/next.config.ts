import type { NextConfig } from "next";

// Where the browser's /api and /ws calls are forwarded. Next bakes rewrites in
// at build time, so the Docker image passes this as a build argument. Behind
// Caddy these rewrites are never used: Caddy routes /api and /ws itself.
const apiUrl = process.env.API_URL ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  output: "standalone",
  async rewrites() {
    return [
      { source: "/api/:path*", destination: `${apiUrl}/api/:path*` },
      { source: "/ws", destination: `${apiUrl}/ws` },
    ];
  },
};

export default nextConfig;
