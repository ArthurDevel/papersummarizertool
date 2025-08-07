/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  async rewrites() {
    return [
      {
        source: '/api/:path*',
        destination: `http://127.0.0.1:${process.env.CONTAINERPORT_API}/:path*`,
      },
    ]
  },
  logging: {
    fetches: {
      fullUrl: true,
    },
  },
}
 
module.exports = nextConfig 