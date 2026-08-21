"use client";

import { usePathname } from "next/navigation";

const LINKS = [
  { href: "/board/", label: "Board" },
  { href: "/record/", label: "Record" },
  { href: "/combo-builder/", label: "Combo" },
];

/**
 * One line at every width, under 80px tall.
 *
 * The current page is marked with a rule under the label rather than a filled
 * pill, so the navigation reads as a set of destinations rather than a set of
 * buttons, and `aria-current` carries the same fact to a screen reader.
 */
export default function Nav() {
  const path = usePathname();
  return (
    <header
      style={{
        position: "sticky",
        top: 0,
        zIndex: "var(--z-sticky)" as unknown as number,
        background: "color-mix(in oklab, var(--bg) 88%, transparent)",
        backdropFilter: "blur(8px)",
        borderBottom: "1px solid var(--line)",
        marginBottom: "var(--s-6)",
      }}
    >
      <div
        className="shell row"
        style={{ height: 62, paddingBottom: 0, flexWrap: "nowrap" }}
      >
        <a
          href="/"
          style={{
            textDecoration: "none",
            fontWeight: 650,
            letterSpacing: "-0.03em",
            fontSize: "1.0625rem",
          }}
        >
          GameSenze
        </a>
        <nav className="cluster" style={{ gap: "var(--s-4)", flexWrap: "nowrap" }}>
          {LINKS.map((link) => {
            const active = path === link.href || path === link.href.slice(0, -1);
            return (
              <a
                key={link.href}
                href={link.href}
                aria-current={active ? "page" : undefined}
                style={{
                  textDecoration: "none",
                  fontSize: "var(--t-small)",
                  color: active ? "var(--ink)" : "var(--ink-2)",
                  paddingBottom: 3,
                  borderBottom: `2px solid ${active ? "var(--ink)" : "transparent"}`,
                  transition: "color var(--dur-2) var(--ease-out)",
                }}
              >
                {link.label}
              </a>
            );
          })}
        </nav>
      </div>
    </header>
  );
}
