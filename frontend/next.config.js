/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",   // enables multi-stage Docker build
  async rewrites() {
    // In production inside Docker, proxy /api/* to the FastAPI backend
    return [
      {
        source: "/api/:path*",
        destination: `${process.env.INTERNAL_API_URL || "http://localhost:8000"}/:path*`,
      },
    ];
  },
};

module.exports = nextConfig;
