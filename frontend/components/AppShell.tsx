import { SiteHeader } from "@/components/SiteHeader";

export function AppShell({
  children,
  wide = false,
}: {
  children: React.ReactNode;
  wide?: boolean;
}) {
  return (
    <div className="blueprint-grid flex min-h-screen flex-col">
      <SiteHeader />
      <main
        className={`mx-auto w-full flex-1 px-5 py-10 md:px-8 md:py-14 ${
          wide ? "max-w-6xl" : "max-w-4xl"
        }`}
      >
        {children}
      </main>
      <footer className="border-t border-line/80 bg-bg-elevated/70">
        <div className="mx-auto flex w-full max-w-6xl flex-col gap-1 px-5 py-5 text-sm text-ink-muted md:flex-row md:items-center md:justify-between md:px-8">
          <p>Manufacturing documentation retrieval with citations and cost guardrails.</p>
          <p className="font-mono text-xs tracking-wide uppercase">Hybrid · Rerank · Grounded</p>
        </div>
      </footer>
    </div>
  );
}
