import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactCompiler: true,
  allowedDevOrigins: [
    "192.168.*.*",  // All 192.168.x.x LAN IPs
    "10.*.*.*",     // All 10.x.x.x private IPs
    "172.*.*.*",    // All 172.x.x.x private IPs
  ],
};

export default nextConfig;
