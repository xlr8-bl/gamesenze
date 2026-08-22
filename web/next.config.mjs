/** @type {import('next').NextConfig} */
const nextConfig = {
  // Static export: Netlify serves files, not a server. The 300-builds/month
  // free tier is the only thing we spend, and there is no runtime to pay for.
  output: "export",
  images: { unoptimized: true },
  trailingSlash: true,
  // @phosphor-icons/react re-exports thousands of icons from one barrel; without
  // this, every dev compile and production build pulls the whole set. This makes
  // Next resolve only the handful of icons actually imported — a large win on
  // build time, dev-compile time and shipped JS alike.
  experimental: { optimizePackageImports: ["@phosphor-icons/react"] },
};

export default nextConfig;
