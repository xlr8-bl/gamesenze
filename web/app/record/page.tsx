"use client";

import { useEffect, useMemo, useState } from "react";
import {
  fetchRecord,
  fetchRecordSummary,
  type RecordRow,
  type RecordSummary,
} from "@/lib/supabase";
import { Empty, Loading, Notice, Result, Signed, Stat } from "@/components/ui";
import UnitsChart from "@/components/UnitsChart";

/**
 * The track record.
 *
 * The important design decision here is what the page does when it does not
 * know something. Under the sample floor the database returns null for every
 * rate, and this page prints the refusal rather than a zero: a hit rate over
 * eleven bets is noise wearing a percentage sign, and showing it would undo
 * the one thing the rest of the site is for.
 */
export default function RecordPage() {
  const [rows, setRows] = useState<RecordRow[] | null>(null);
  const [summary, setSummary] = useState<RecordSummary[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [sport, setSport] = useState("all");
  // A 34-row table is a wall, not a record. The chart carries the shape of the
  // whole history; the table starts at the length someone will actually read
  // and opens on request.
  const [showAll, setShowAll] = useState(false);
  const PREVIEW = 12;

  useEffect(() => {
    let live = true;
    Promise.all([fetchRecord(), fetchRecordSummary()])
      .then(([r, s]) => {
        if (!live) return;
        setRows(r);
        setSummary(s);
      })
      .catch((e) => live && setError(String(e?.message ?? e)));
    return () => {
      live = false;
    };
  }, []);

  const sports = useMemo(
    () => summary.map((s) => s.sport).filter((s) => s !== "all").sort(),
    [summary],
  );
  const head = summary.find((s) => s.sport === sport);
  const visible = useMemo(
    () => (rows ?? []).filter((r) => sport === "all" || r.sport === sport),
    [rows, sport],
  );
  const shown = showAll ? visible : visible.slice(0, PREVIEW);

  if (error) {
    return (
      <main className="stack">
        <Notice tone="bad">The record could not be loaded: {error}</Notice>
      </main>
    );
  }
  if (rows === null) return <Loading label="Loading the record" />;

  if (rows.length === 0) {
    return (
      <main className="stack">
        <h1>Record</h1>
        <Empty title="Nothing has settled yet">
          Every pick we publish lands here once its fixture finishes, won or
          lost, with the price we published and the price the market closed at.
          Nothing is removed from this page after the fact.
        </Empty>
      </main>
    );
  }

  return (
    <main className="stack">
      <div className="row">
        <h1>Record</h1>
        {sports.length > 1 && (
          <div className="seg" role="group" aria-label="Filter by sport">
            {["all", ...sports].map((s) => (
              <button
                key={s}
                aria-pressed={sport === s}
                onClick={() => setSport(s)}
              >
                {s === "all" ? "All" : s}
              </button>
            ))}
          </div>
        )}
      </div>

      {head && <Headline summary={head} />}

      <div className="panel">
        <UnitsChart rows={visible} />
      </div>

      <div className="panel panel-flush">
        <div className="table-scroll">
          <table>
            <caption
              style={{
                captionSide: "top",
                textAlign: "left",
                padding: "var(--s-4) var(--s-5) var(--s-3)",
                color: "var(--ink-3)",
                fontSize: "var(--t-small)",
              }}
            >
              Every settled pick, newest first. CLV compares the price we
              published against the price the market closed at.
            </caption>
            <thead>
              <tr>
                <th style={{ paddingLeft: "var(--s-5)" }}>Fixture</th>
                <th>Selection</th>
                <th className="right">Published</th>
                <th className="right">Closed</th>
                <th className="right">CLV</th>
                <th style={{ paddingRight: "var(--s-5)" }}>Result</th>
              </tr>
            </thead>
            <tbody>
              {shown.map((r) => (
                <tr key={r.id}>
                  <td style={{ paddingLeft: "var(--s-5)" }}>
                    <div>
                      {r.home_team} v {r.away_team}
                    </div>
                    <div
                      className="num"
                      style={{ color: "var(--ink-3)", fontSize: "var(--t-micro)" }}
                    >
                      {r.kickoff_at.slice(0, 10)}
                    </div>
                  </td>
                  <td>
                    {r.selection}
                    <div style={{ color: "var(--ink-3)", fontSize: "var(--t-micro)" }}>
                      {r.market}
                    </div>
                  </td>
                  <td className="right num">
                    {r.capture_odds ? Number(r.capture_odds).toFixed(2) : "n/a"}
                  </td>
                  <td className="right num" style={{ color: "var(--ink-2)" }}>
                    {r.closing_odds ? Number(r.closing_odds).toFixed(2) : "n/a"}
                  </td>
                  <td className="right">
                    <Signed
                      value={r.clv_pct === null ? null : Number(r.clv_pct)}
                      suffix="%"
                      digits={1}
                    />
                  </td>
                  <td style={{ paddingRight: "var(--s-5)" }}>
                    <Result result={r.result} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {visible.length > PREVIEW && (
          <div
            style={{
              borderTop: "1px solid var(--line)",
              padding: "var(--s-3) var(--s-5)",
            }}
          >
            <button
              className="btn btn-quiet btn-sm"
              onClick={() => setShowAll((v) => !v)}
              aria-expanded={showAll}
            >
              {showAll
                ? `Show the most recent ${PREVIEW}`
                : `Show all ${visible.length} settled picks`}
            </button>
          </div>
        )}
      </div>
    </main>
  );
}

function Headline({ summary: s }: { summary: RecordSummary }) {
  const settledDecided = s.won + s.lost;
  return (
    <div className="stack-s">
      <div
        className="panel"
        style={{
          display: "grid",
          gap: "var(--s-5)",
          gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))",
        }}
      >
        <Stat
          label="Settled picks"
          value={s.settled}
          note={s.pushed > 0 ? `${s.pushed} void or pushed` : undefined}
          size="xl"
        />
        <Stat
          label="Hit rate"
          value={
            s.hit_rate_pct === null ? (
              <span style={{ color: "var(--ink-3)" }}>held</span>
            ) : (
              `${Number(s.hit_rate_pct).toFixed(1)}%`
            )
          }
          note={`${s.won} of ${settledDecided} decided`}
          size="xl"
        />
        <Stat
          label="Return, level stakes"
          value={
            s.roi_pct === null ? (
              <span style={{ color: "var(--ink-3)" }}>held</span>
            ) : (
              <Signed value={Number(s.roi_pct)} suffix="%" digits={1} />
            )
          }
          note={`${Number(s.units).toFixed(2)} units`}
          size="xl"
        />
        <Stat
          label="Closing line value"
          value={
            s.avg_clv_pct === null ? (
              <span style={{ color: "var(--ink-3)" }}>held</span>
            ) : (
              <Signed value={Number(s.avg_clv_pct)} suffix="%" digits={2} />
            )
          }
          note={`${s.clv_sample} with a closing price`}
          size="xl"
        />
      </div>

      {!s.rates_published && (
        <Notice tone="caution">
          Rates are withheld below {s.sample_floor} settled picks. We have{" "}
          {s.settled}. The counts above are real and complete; the percentages
          are not shown because at this sample they would describe luck rather
          than method. They appear on their own once the sample reaches the
          floor.
        </Notice>
      )}
      {s.rates_published && s.clv_sample < s.sample_floor && (
        <Notice>
          Closing line value is still withheld: only {s.clv_sample} of{" "}
          {s.settled} settled picks have a captured closing price, below the{" "}
          {s.sample_floor} needed.
        </Notice>
      )}
    </div>
  );
}
