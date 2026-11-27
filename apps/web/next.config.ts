import type { NextConfig } from "next";

// The browser only ever talks to this Next.js origin. API calls are proxied to FastAPI so
// session cookies stay first-party, SameSite=Lax, and no CORS configuration is needed.
const apiOrigin = process.env.API_INTERNAL_URL ?? "http://localhost:8100";

const securityHeaders = [
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
];

const nextConfig: NextConfig = {
  // A self-contained server bundle for the production image (apps/web/Dockerfile).
  output: "standalone",
  cacheComponents: true,
  experimental: {
    // The signed-in workspace is rendered in the browser after the session check (see
    // app/(app)/layout.tsx), so its pages can't be part of a prerendered shell and every one
    // of them would be reported as "could not validate instant navigation". Validate only the
    // segments that opt in with `export const instant = true`.
    instantInsights: { validationLevel: "manual-warning" },
  },
  partialPrefetching: true,
  poweredByHeader: false,
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${apiOrigin}/api/:path*` }];
  },
  async redirects() {
    return [{ source: "/", destination: "/overview", permanent: false }];
  },
  async headers() {
    return [{ source: "/:path*", headers: securityHeaders }];
  },
};

export default nextConfig;
