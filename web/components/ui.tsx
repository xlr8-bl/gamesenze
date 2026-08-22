"use client";

import type { CSSProperties, ReactNode } from "react";
import {
  CheckCircle,
  Circle,
  Info,
  MinusCircle,
  Warning,
  XCircle,
} from "@phosphor-icons/react";

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
 * Green and red is the convention a bettor expects, and it is also the pair
 * that colourblind readers struggle with most: these two sit at dE 9.2 under
 * deuteranopia, which is above the floor only because the glyph and the word
 * are doing work alongside the colour. Never render one of these as a bare
 * coloured dot.
 */
export function Result({ result }: { result: string | null }) {
  if (result === "won") {
    return (
      <span className="status status-won">
        <CheckCircle size={16} weight="fill" aria-hidden />
        Won
      </span>
    );
  }
  if (result === "lost") {
    return (
      <span className="status status-lost">
        <XCircle size={16} weight="fill" aria-hidden />
        Lost
      </span>
    );
  }
  if (result === "push" || result === "void") {
    return (
      <span className="status status-neutral">
        <MinusCircle size={16} weight="fill" aria-hidden />
        {result === "push" ? "Push" : "Void"}
      </span>
    );
  }
  return (
    <span className="status status-neutral">
      <Circle size={16} aria-hidden />
      Open
    </span>
  );
}

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
    return <span className="num sign-nil">held</span>;
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
 * A stat tile. `value` may be a withheld marker rather than a number, because
 * this product refuses to print a rate it cannot stand behind, and a zero in
 * that slot would be read as a measurement.
 */
export function Stat({
  label,
  value,
  note,
  tone,
}: {
  label: string;
  value: ReactNode;
  note?: ReactNode;
  tone?: "brand" | "won" | "lost";
}) {
  const color =
    tone === "brand" ? "var(--brand)" : tone === "won" ? "var(--won)" : tone === "lost" ? "var(--lost)" : "var(--ink)";
  return (
    <div>
      <div className="label">{label}</div>
      <div
        className="cond num"
        style={{
          color,
          fontWeight: 700,
          fontSize: "clamp(1.9rem, 1.5rem + 1.6vw, 2.6rem)",
          lineHeight: 1.05,
          margin: "2px 0 1px",
        }}
      >
        {value}
      </div>
      {note && (
        <div style={{ color: "var(--ink-3)", fontSize: "var(--t-micro)" }}>{note}</div>
      )}
    </div>
  );
}

export function Chip({
  children,
  variant,
  style,
}: {
  children: ReactNode;
  variant?: "brand" | "outline-brand";
  style?: CSSProperties;
}) {
  return (
    <span className={`chip${variant ? ` chip-${variant}` : ""}`} style={style}>
      {children}
    </span>
  );
}

export function Loading({ label }: { label: string }) {
  return (
    <div className="panel panel-pad" role="status" aria-live="polite">
      <div className="cluster" style={{ color: "var(--ink-2)" }}>
        <span className="spinner" aria-hidden />
        {label}
      </div>
    </div>
  );
}

export function Empty({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="panel panel-pad">
      <h2 className="cond" style={{ marginBottom: "var(--s-2)", textTransform: "uppercase", letterSpacing: "0.02em" }}>
        {title}
      </h2>
      <p style={{ color: "var(--ink-2)", marginBottom: 0 }}>{children}</p>
    </div>
  );
}
