/** @type {import('next').NextConfig} */
function safeOrigin(value) {
  if (!value) return null;

  try {
    return new URL(value).origin;
  } catch {
    return null;
  }
}

const supabaseOrigin =
  safeOrigin(process.env.NEXT_PUBLIC_SUPABASE_URL) ??
  "https://jcyfhfpulckpsdaiecoe.supabase.co";
const supabaseWs = supabaseOrigin.replace(/^https:/, "wss:");
const aeeOrigin = safeOrigin(process.env.AEE_BACKEND_URL);

const connectSrc = [
  "'self'",
  supabaseOrigin,
  supabaseWs,
  ...(aeeOrigin ? [aeeOrigin] : [])
].join(" ");

const contentSecurityPolicy = [
  "default-src 'self'",
  "base-uri 'self'",
  "object-src 'none'",
  "frame-ancestors 'none'",
  "form-action 'self'",
  "script-src 'self' 'unsafe-inline'",
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data: blob:",
  "font-src 'self' data:",
  `connect-src ${connectSrc}`,
  "worker-src 'self' blob:",
  "manifest-src 'self'"
].join("; ");

const nextConfig = {
  output: "standalone",
  reactStrictMode: true,
  poweredByHeader: false,
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          {
            key: "Content-Security-Policy",
            value: contentSecurityPolicy
          },
          {
            key: "Strict-Transport-Security",
            value: "max-age=31536000; includeSubDomains"
          },
          {
            key: "X-Content-Type-Options",
            value: "nosniff"
          },
          {
            key: "X-Frame-Options",
            value: "DENY"
          },
          {
            key: "Referrer-Policy",
            value: "strict-origin-when-cross-origin"
          },
          {
            key: "Permissions-Policy",
            value:
              "camera=(), microphone=(), geolocation=(), payment=(), usb=()"
          },
          {
            key: "Cross-Origin-Opener-Policy",
            value: "same-origin"
          },
          {
            key: "X-DNS-Prefetch-Control",
            value: "off"
          }
        ]
      }
    ];
  }
};

export default nextConfig;
