"use client";

import type { ReactNode } from "react";
import {
  CheckCircle,
  Circle,
  Info,
  MinusCircle,
  Warning,
  XCircle,
} from "@phosphor-icons/react";

/* ---------------------------------------------------------------------------
   Primitives.

   Every one of these is a client leaf: the pages that use them stay as light
   as a static export allows, and the only JavaScript that ships is the
   JavaScript that has to.
--------------------------------------------------------------------------- */

export function Notice({
  tone = "neutral",
  children,
}: {
  tone?: "neutral" | "caution" | "bad";
  children: ReactNode;
}) {
  const Icon = tone === "neutral" ? Info : tone === "caution" ? Warning : XCircle;
  return (
    <div
      className={`notice${tone === "neutral" ? "" : ` notice-${tone}`}`}
      role={tone === "bad" ? "alert" : undefined}
    >
      <Icon size={16} weight="bold" aria-hidden />
      <div>{children}</div>
    </div>
  );
}

/**
 * A settled result.
 *
 * Colour is a second channel here, never the only one. The glyph and the word
 * both survive colourblindness, greyscale and forced-colours mode, which is
 * exactly the case the record page has to survive: won and lost sitting in the
 * same column, read at a glance.
 */
export function Result({ result }: { result: string | null }) {
  if (result === "won") {
    return (
      <span className="status status-won">
        <CheckCircle size={15} weight="fill" aria-hidden />
        Won
      </span>
    );
  }
  if (result === "lost") {
    return (
      <span className="status status-lost">
        <XCircle size={15} weight="fill" aria-hidden />
        Lost
      </span>
    );
  }
  if (result === "push" || result === "void") {
    return (
      <span className="status status-neutral">
        <MinusCircle size={15} weight="fill" aria-hidden />
        {result === "push" ? "Push" : "Void"}
      </span>
    );
  }
  return (
    <span className="status status-neutral">
      <Circle size={15} aria-hidden />
      Open
    </span>
  );
}

/** A signed number, where the sign is the information. */
export function Signed({
  value,
  suffix = "",
  digits = 2,
}: {
  value: number | null;
  suffix?: string;
  digits?: number;
}) {
  if (value === null || Number.isNaN(value)) {
    return <span className="num sign-nil">not yet</span>;
  }
  const cls = value > 0 ? "sign-pos" : value < 0 ? "sign-neg" : "sign-nil";
  return (
    <span className={`num ${cls}`}>
      {value > 0 ? "+" : ""}
      {value.toFixed(digits)}
      {suffix}
    </span>
  );
}

/**
 * A stat tile.
 *
 * `value` is null when we hold a number back rather than publish it under the
 * sample floor. The tile says so in words instead of printing a zero, because
 * a zero would be read as a measurement.
 */
export function Stat({
  label,
  value,
  note,
  size = "lg",
}: {
  label: string;
  value: ReactNode;
  note?: ReactNode;
  size?: "lg" | "xl";
}) {
  return (
    <div>
      <div style={{ color: "var(--ink-3)", fontSize: "var(--t-small)" }}>{label}</div>
      <div className={`num num-${size}`} style={{ margin: "2px 0 1px" }}>
        {value}
      </div>
      {note && (
        <div style={{ color: "var(--ink-3)", fontSize: "var(--t-micro)" }}>{note}</div>
      )}
    </div>
  );
}

export function Tag({
  children,
  strong = false,
}: {
  children: ReactNode;
  strong?: boolean;
}) {
  return <span className={`tag${strong ? " tag-strong" : ""}`}>{children}</span>;
}

/** Loading state. Shown as structure, so nothing jumps when the data lands. */
export function Loading({ label }: { label: string }) {
  return (
    <div className="panel" role="status" aria-live="polite">
      <div className="cluster" style={{ color: "var(--ink-2)" }}>
        <span className="spinner" aria-hidden />
        {label}
      </div>
    </div>
  );
}

/** Empty state. A quiet board is an outcome, not a failure, and it says so. */
export function Empty({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="panel">
      <h2 style={{ marginBottom: "var(--s-2)" }}>{title}</h2>
      <p style={{ color: "var(--ink-2)", marginBottom: 0 }}>{children}</p>
    </div>
  );
}
