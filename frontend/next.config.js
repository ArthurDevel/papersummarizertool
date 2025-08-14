/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  async rewrites() {
    return [
      {
        source: '/api/:path*',
        destination: `http://127.0.0.1:${process.env.NEXT_PUBLIC_CONTAINERPORT_API}/:path*`,
        //destination: `http://127.0.0.1:8010/:path*`,
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