/** @type {import('next').NextConfig} */
const nextConfig = {
  // Static export: Netlify serves files, not a server. The 300-builds/month
  // free tier is the only thing we spend, and there is no runtime to pay for.
  output: "export",
  images: { unoptimized: true },
  trailingSlash: true,
};

export default nextConfig;
