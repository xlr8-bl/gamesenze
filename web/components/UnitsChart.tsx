"use client";

import { useId, useMemo, useState } from "react";
import type { RecordRow } from "@/lib/supabase";

/**
 * Cumulative level-stake units, oldest settled pick to newest.
 *
 * One series, so there is no legend: the title names it and the line is
 * direct-labelled at its end. One y-axis, because a second scale on the same
 * plot is the fastest way to make two unrelated things look correlated.
 *
 * The zero line is drawn as a real reference, not as a grid line, because
 * crossing it is the only event on this chart that means anything.
 */
export default function UnitsChart({ rows }: { rows: RecordRow[] }) {
  const gradId = useId();
  const [hover, setHover] = useState<number | null>(null);

  const series = useMemo(() => {
    const ordered = [...rows]
      .filter((r) => r.settled_at)
      .sort((a, b) => (a.settled_at ?? "").localeCompare(b.settled_at ?? ""));
    let acc = 0;
    return ordered.map((r, i) => {
      acc += Number(r.unit_return ?? 0);
      return { i, units: acc, row: r };
    });
  }, [rows]);

  if (series.length < 2) return null;

  const W = 720;
  const H = 200;
  const PAD = { t: 12, r: 52, b: 22, l: 8 };
  const values = series.map((p) => p.units);
  const lo = Math.min(0, ...values);
  const hi = Math.max(0, ...values);
  const span = hi - lo || 1;
  const x = (i: number) =>
    PAD.l + (i / (series.length - 1)) * (W - PAD.l - PAD.r);
  const y = (v: number) =>
    PAD.t + (1 - (v - lo) / span) * (H - PAD.t - PAD.b);

  const path = series.map((p, i) => `${i ? "L" : "M"}${x(p.i)},${y(p.units)}`).join(" ");
  const area = `${path} L${x(series.length - 1)},${y(0)} L${x(0)},${y(0)} Z`;
  const last = series[series.length - 1];
  const span_days = (a?: string | null, b?: string | null) =>
    a && b ? `${a.slice(0, 10)} to ${b.slice(0, 10)}` : "";
  const dates = span_days(series[0].row.settled_at, last.row.settled_at);
  const active = hover !== null ? series[hover] : null;
  const up = last.units >= 0;

  return (
    <figure style={{ margin: 0 }}>
      <figcaption
        className="row"
        style={{ marginBottom: "var(--s-3)", alignItems: "baseline" }}
      >
        <h2 className="cond" style={{ textTransform: "uppercase", letterSpacing: "0.04em" }}>
          Cumulative units, one unit per pick
        </h2>
        <span className="num" style={{ color: "var(--ink-3)", fontSize: "var(--t-micro)" }}>
          {dates}
        </span>
      </figcaption>

      <div style={{ position: "relative" }}>
        <svg
          viewBox={`0 0 ${W} ${H}`}
          width="100%"
          height={H}
          role="img"
          aria-label={`Cumulative return over ${series.length} settled picks, level stakes, ending at ${last.units.toFixed(2)} units`}
          onMouseLeave={() => setHover(null)}
          onMouseMove={(e) => {
            const box = e.currentTarget.getBoundingClientRect();
            const px = ((e.clientX - box.left) / box.width) * W;
            const idx = Math.round(
              ((px - PAD.l) / (W - PAD.l - PAD.r)) * (series.length - 1),
            );
            setHover(Math.max(0, Math.min(series.length - 1, idx)));
          }}
          style={{ display: "block", touchAction: "pan-y" }}
        >
          <defs>
            <linearGradient id={gradId} x1="0" y1="0" x2="0" y2="1">
              <stop
                offset="0%"
                stopColor={up ? "var(--brand)" : "var(--lost)"}
                stopOpacity="0.28"
              />
              <stop
                offset="100%"
                stopColor={up ? "var(--brand)" : "var(--lost)"}
                stopOpacity="0"
              />
            </linearGradient>
          </defs>

          {/* Break-even. The only reference line on the plot. */}
          <line
            x1={PAD.l}
            x2={W - PAD.r}
            y1={y(0)}
            y2={y(0)}
            stroke="var(--line-firm)"
            strokeWidth="1"
            strokeDasharray="3 3"
          />
          <text
            x={W - PAD.r + 6}
            y={y(0) + 4}
            fill="var(--ink-3)"
            fontSize="10"
            fontFamily="var(--cond)"
          >
            0
          </text>

          <path d={area} fill={`url(#${gradId})`} />
          <path
            d={path}
            fill="none"
            stroke={up ? "var(--brand)" : "var(--lost)"}
            strokeWidth="2"
            strokeLinejoin="round"
            strokeLinecap="round"
          />

          {/* Direct label at the end of the line, instead of a legend box. */}
          <circle
            cx={x(last.i)}
            cy={y(last.units)}
            r="4"
            fill={up ? "var(--brand)" : "var(--lost)"}
            stroke="var(--surface)"
            strokeWidth="2"
          />
          <text
            x={x(last.i) + 10}
            y={y(last.units) + 4}
            fill="var(--ink-2)"
            fontSize="11"
            fontFamily="var(--cond)"
          >
            {last.units > 0 ? "+" : ""}
            {last.units.toFixed(1)}
          </text>

          {active && (
            <>
              <line
                x1={x(active.i)}
                x2={x(active.i)}
                y1={PAD.t}
                y2={H - PAD.b}
                stroke="var(--line-firm)"
                strokeWidth="1"
              />
              <circle
                cx={x(active.i)}
                cy={y(active.units)}
                r="4"
                fill="var(--ink)"
                stroke="var(--surface)"
                strokeWidth="2"
              />
            </>
          )}
        </svg>

        {active && (
          <div
            role="status"
            style={{
              position: "absolute",
              top: 0,
              left: `${Math.min(72, (x(active.i) / W) * 100)}%`,
              background: "var(--raised)",
              border: "1px solid var(--line-firm)",
              borderRadius: "var(--r-2)",
              padding: "var(--s-2) var(--s-3)",
              fontSize: "var(--t-micro)",
              pointerEvents: "none",
              whiteSpace: "nowrap",
              maxWidth: "60%",
              overflow: "hidden",
              textOverflow: "ellipsis",
            }}
          >
            <div style={{ color: "var(--ink)" }}>
              {active.row.home_team} v {active.row.away_team}
            </div>
            <div style={{ color: "var(--ink-3)" }}>
              {active.row.result} <span className="num">
                {active.units > 0 ? "+" : ""}
                {active.units.toFixed(2)}
              </span>{" "}
              units after
            </div>
          </div>
        )}
      </div>
    </figure>
  );
}
