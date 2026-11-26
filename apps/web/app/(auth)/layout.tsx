import { CircleCheck } from "lucide-react";
import Link from "next/link";
import { PoweredBy, ProductMark } from "@/components/powered-by";
import { brand } from "@/lib/brand";

const POINTS = [
  "See every website, computer, server and network device you protect",
  "Get plain-English alerts and clear next steps",
  "Share monthly security reports with management",
];

export default function AuthLayout({ children }: LayoutProps<"/">) {
  return (
    <div className="grid min-h-screen lg:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)]">
      <aside className="relative hidden overflow-hidden bg-navy p-10 text-white lg:flex lg:flex-col">
        <div
          className="pointer-events-none absolute inset-0 opacity-40"
          style={{
            background:
              "radial-gradient(60rem 30rem at 0% 0%, rgba(37,99,235,.35), transparent 60%), radial-gradient(40rem 30rem at 100% 100%, rgba(124,58,237,.25), transparent 60%)",
          }}
          aria-hidden
        />
        <div className="relative">
          <Link href="/login" aria-label={brand.productName}>
            <ProductMark inverted />
          </Link>
        </div>
        <div className="relative mt-auto max-w-md">
          <h2 className="text-3xl leading-tight font-semibold tracking-tight">
            Cybersecurity your business can actually see.
          </h2>
          <p className="mt-3 text-slate-300">{brand.tagline}</p>
          <ul className="mt-8 space-y-3">
            {POINTS.map((p) => (
              <li key={p} className="flex gap-3 text-sm text-slate-200">
                <CircleCheck className="mt-0.5 size-4 shrink-0 text-blue-400" aria-hidden />
                {p}
              </li>
            ))}
          </ul>
        </div>
        <div className="relative mt-auto pt-10">
          <PoweredBy inverted />
        </div>
      </aside>
      <main className="flex flex-col px-5 py-8 sm:px-10">
        <div className="lg:hidden">
          <ProductMark />
        </div>
        <div className="mx-auto flex w-full max-w-[26rem] flex-1 flex-col justify-center py-10">
          {children}
        </div>
        <footer className="flex flex-col items-center gap-3 text-xs text-subtle sm:flex-row sm:justify-between">
          <div className="flex gap-4">
            <Link href="/legal/privacy" className="hover:text-fg">
              Privacy
            </Link>
            <Link href="/legal/terms" className="hover:text-fg">
              Terms
            </Link>
          </div>
          <PoweredBy className="lg:hidden" />
        </footer>
      </main>
    </div>
  );
}
