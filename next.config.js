const path = require('path');

/** @type {import('next').NextConfig} */
const nextConfig = {
  webpack: (config) => {
    config.resolve.alias = {
      ...(config.resolve.alias ?? {}),
      '@': path.resolve(process.cwd()),
    };
    return config;
  },
  async rewrites() {
    // Only proxy to Flask when FLASK_PROXY=true (run both: python run.py + npm run dev)
    if (process.env.FLASK_PROXY !== 'true') return [];
    const flaskBackend = process.env.FLASK_URL || 'http://localhost:5000';
    return [
      { source: '/team', destination: `${flaskBackend}/team` },
      { source: '/challengers', destination: `${flaskBackend}/challengers` },
      { source: '/challengers/prizepicks', destination: `${flaskBackend}/challengers/prizepicks` },
      { source: '/prizepicks', destination: `${flaskBackend}/prizepicks` },
      { source: '/moneylines', destination: `${flaskBackend}/moneylines` },
      { source: '/edge', destination: `${flaskBackend}/edge` },
      { source: '/api/:path*', destination: `${flaskBackend}/api/:path*` },
    ];
  },
};

module.exports = nextConfig;
