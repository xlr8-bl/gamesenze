"use client";

import { useEffect, useState } from "react";
import { usePathname } from "next/navigation";
import { List, X } from "@phosphor-icons/react";
import { fetchLive } from "@/lib/supabase";

const LINKS = [
  { href: "/live/", label: "Live" },
  { href: "/board/", label: "Board" },
  { href: "/record/", label: "Record" },
  { href: "/combo-builder/", label: "Combo" },
  { href: "/pricing/", label: "Pricing" },
];

/**
 * One line at desktop, a sheet on a phone.
 *
 * The header goes translucent only once the page has scrolled under it; at the
 * top it sits flush on the ground so the hero art runs all the way up.
 */
export default function Nav() {
  const path = usePathname();
  const [open, setOpen] = useState(false);
  const [stuck, setStuck] = useState(false);
  const [liveCount, setLiveCount] = useState(0);

  useEffect(() => {
    let on = true;
    const load = () => fetchLive().then((m) => on && setLiveCount(m.length)).catch(() => {});
    load();
    const id = setInterval(load, 45_000);
    return () => {
      on = false;
      clearInterval(id);
    };
  }, []);

  useEffect(() => {
    // IntersectionObserver on a sentinel, not a scroll listener: this fires
    // twice in the life of the page rather than on every frame.
    const sentinel = document.createElement("div");
    sentinel.style.cssText = "position:absolute;top:0;height:8px;width:1px";
    document.body.appendChild(sentinel);
    const io = new IntersectionObserver(([e]) => setStuck(!e.isIntersecting), {
      threshold: 0,
    });
    io.observe(sentinel);
    return () => {
      io.disconnect();
      sentinel.remove();
    };
  }, []);

  useEffect(() => setOpen(false), [path]);

  return (
    <header
      style={{
        position: "sticky",
        top: 0,
        zIndex: 100,
        background: stuck ? "color-mix(in oklab, var(--bg) 82%, transparent)" : "transparent",
        backdropFilter: stuck ? "blur(14px) saturate(1.4)" : "none",
        borderBottom: `1px solid ${stuck ? "var(--line)" : "transparent"}`,
        transition: "background-color 200ms var(--ease-out), border-color 200ms var(--ease-out)",
      }}
    >
      <div className="shell row" style={{ height: 68, flexWrap: "nowrap" }}>
        <a
          href="/"
          className="cond"
          style={{
            textDecoration: "none",
            fontWeight: 700,
            fontSize: "1.5rem",
            letterSpacing: "0.01em",
            textTransform: "uppercase",
            display: "inline-flex",
            alignItems: "center",
            gap: 9,
          }}
        >
          <span
            aria-hidden
            style={{
              width: 10,
              height: 26,
              borderRadius: 3,
              background: "var(--brand)",
              boxShadow: "0 0 16px -2px var(--brand)",
            }}
          />
          GameSenze
        </a>

        <nav className="cluster" style={{ gap: "var(--s-5)", flexWrap: "nowrap" }} aria-label="Main">
          <div className="nav-links cluster" style={{ gap: "var(--s-5)", flexWrap: "nowrap" }}>
            {LINKS.map((link) => {
              const active = path === link.href;
              return (
                <a
                  key={link.href}
                  href={link.href}
                  aria-current={active ? "page" : undefined}
                  className="cond"
                  style={{
                    // WCAG 2.5.8: a standalone control needs at least 24px of
                    // target, and a 16px line of text is not one.
                    display: "inline-flex",
                    alignItems: "center",
                    gap: 6,
                    minHeight: 32,
                    padding: "0 2px",
                    textDecoration: "none",
                    fontWeight: 600,
                    fontSize: "1rem",
                    letterSpacing: "0.07em",
                    textTransform: "uppercase",
                    color: active ? "var(--brand)" : "var(--ink-2)",
                    transition: "color 200ms var(--ease-out)",
                  }}
                >
                  {link.label}
                  {link.href === "/live/" && liveCount > 0 && (
                    <span className="live-dot" aria-label={`${liveCount} live`} />
                  )}
                </a>
              );
            })}
          </div>
          <a href="/signin/" className="btn btn-sm nav-cta">
            Sign in
          </a>
          <button
            type="button"
            className="btn btn-quiet nav-toggle"
            aria-expanded={open}
            aria-label={open ? "Close menu" : "Open menu"}
            onClick={() => setOpen((v) => !v)}
          >
            {open ? <X size={22} weight="bold" /> : <List size={22} weight="bold" />}
          </button>
        </nav>
      </div>

      {open && (
        <div
          className="shell rise"
          style={{
            paddingBottom: "var(--s-4)",
            display: "grid",
            gap: "var(--s-2)",
            background: "var(--bg)",
            borderBottom: "1px solid var(--line)",
          }}
        >
          {LINKS.map((link) => (
            <a
              key={link.href}
              href={link.href}
              className="cond"
              style={{
                textDecoration: "none",
                fontWeight: 600,
                fontSize: "1.25rem",
                letterSpacing: "0.06em",
                textTransform: "uppercase",
                color: path === link.href ? "var(--brand)" : "var(--ink)",
                padding: "10px 0",
                borderBottom: "1px solid var(--line)",
              }}
            >
              {link.label}
            </a>
          ))}
          <a href="/signin/" className="btn" style={{ marginTop: "var(--s-2)" }}>
            Sign in
          </a>
        </div>
      )}
    </header>
  );
}
