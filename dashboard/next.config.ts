import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Dev-only: allows viewing the dev server from this machine's LAN IP
  // (e.g. testing from another device), not just localhost.
  allowedDevOrigins: ["10.147.21.251"],
};

export default nextConfig;
