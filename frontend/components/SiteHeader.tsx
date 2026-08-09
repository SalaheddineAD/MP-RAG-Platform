"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { fetchHealth } from "@/lib/api";

const links = [
  { href: "/", label: "Query" },
  { href: "/ingest", label: "Ingest" },
  { href: "/metrics", label: "Metrics" },
  { href: "/evaluate", label: "Evaluate" },
];

export function SiteHeader() {
  const pathname = usePathname();
  const [online, setOnline] = useState<boolean | null>(null);

  useEffect(() => {
    let cancelled = false;

    const check = async () => {
      try {
        const health = await fetchHealth();
        if (!cancelled) setOnline(health.status === "healthy");
      } catch {
        if (!cancelled) setOnline(false);
      }
    };

    check();
    const id = window.setInterval(check, 15000);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, []);

  return (
    <header className="border-b border-line/80 bg-bg-elevated/85 backdrop-blur-md">
      <div className="mx-auto flex w-full max-w-6xl items-center justify-between gap-6 px-5 py-4 md:px-8">
        <Link href="/" className="group flex items-baseline gap-2">
          <span className="font-mono text-[11px] tracking-[0.22em] text-accent uppercase">
            MP
          </span>
          <span className="text-lg font-medium tracking-tight text-ink transition-colors group-hover:text-accent-strong">
            RAG Platform
          </span>
        </Link>

        <nav className="hidden items-center gap-1 sm:flex">
          {links.map((link) => {
            const active =
              link.href === "/"
                ? pathname === "/"
                : pathname.startsWith(link.href);
            return (
              <Link
                key={link.href}
                href={link.href}
                className={`relative px-3 py-2 text-sm transition-colors ${
                  active
                    ? "text-ink"
                    : "text-ink-muted hover:text-ink"
                }`}
              >
                {link.label}
                {active ? (
                  <span className="nav-underline absolute inset-x-3 bottom-1 h-px bg-accent" />
                ) : null}
              </Link>
            );
          })}
        </nav>

        <div className="flex items-center gap-2 font-mono text-[11px] tracking-wide text-ink-muted uppercase">
          <span
            className={`h-2 w-2 rounded-full ${
              online === null
                ? "bg-line"
                : online
                  ? "bg-good"
                  : "bg-bad"
            }`}
            aria-hidden
          />
          <span>{online === null ? "Checking" : online ? "API online" : "API offline"}</span>
        </div>
      </div>

      <nav className="flex gap-1 overflow-x-auto border-t border-line/70 px-3 py-2 sm:hidden">
        {links.map((link) => {
          const active =
            link.href === "/"
              ? pathname === "/"
              : pathname.startsWith(link.href);
          return (
            <Link
              key={link.href}
              href={link.href}
              className={`whitespace-nowrap px-3 py-1.5 text-sm ${
                active ? "text-accent" : "text-ink-muted"
              }`}
            >
              {link.label}
            </Link>
          );
        })}
      </nav>
    </header>
  );
}
