// Product identity is configuration, not code. Change these through environment variables
// (NEXT_PUBLIC_*) at build time to rebrand without touching components.
export const brand = {
  productName: process.env.NEXT_PUBLIC_PRODUCT_NAME ?? "SME Cybersecurity Monitoring",
  shortName: process.env.NEXT_PUBLIC_PRODUCT_SHORT_NAME ?? "SME Cyber Monitor",
  tagline:
    process.env.NEXT_PUBLIC_PRODUCT_TAGLINE ??
    "Business cybersecurity visibility, monitoring and risk management in one platform.",
  poweredByName: process.env.NEXT_PUBLIC_POWERED_BY_NAME ?? "GraceGate Technologies",
  poweredByLogo: process.env.NEXT_PUBLIC_POWERED_BY_LOGO ?? "/brand/gracegate-technologies-logo.jpg",
};
