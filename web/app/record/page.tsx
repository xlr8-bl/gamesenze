"use client";

import { useEffect, useMemo, useState } from "react";
import {
  fetchRecord,
  fetchRecordSummary,
  type RecordRow,
  type RecordSummary,
} from "@/lib/supabase";
import { Empty, Loading, Notice, Result, Signed, Stat } from "@/components/ui";
import { CompetitionMark } from "@/components/sport";
import UnitsChart from "@/components/UnitsChart";
import PageHead from "@/components/PageHead";
import { selectionLabel, marketLabel } from "@/lib/analysis";
import { CountUp, Reveal } from "@/components/motion";

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
      <div className="shell stack" style={{ paddingTop: "var(--s-6)" }}>
        <Notice tone="bad">The record could not be loaded: {error}</Notice>
      </div>
    );
  }
  if (rows === null)
    return (
      <div className="shell" style={{ paddingTop: "var(--s-6)" }}>
        <Loading label="Loading the record" />
      </div>
    );

  if (rows.length === 0) {
    return (
      <div className="shell stack" style={{ paddingTop: "var(--s-6)" }}>
        <h1 className="poster" style={{ fontSize: "clamp(2rem, 1.5rem + 2.4vw, 3.25rem)" }}>
          The record
        </h1>
        <Empty title="Nothing has settled yet">
          Every pick we publish lands here once its fixture finishes, won or
          lost, with the price we published and the price the market closed at.
          Nothing is removed from this page after the fact.
        </Empty>
      </div>
    );
  }

  return (
    <>
      <PageHead
        eyebrow="Every settled pick"
        title="The record"
        lede="Published in full, losses included. Rates stay withheld until the sample is big enough to mean anything."
        photoFrom="ucl"
      />
      <div className="shell stack" style={{ paddingTop: "var(--s-6)" }}>
      <div className="row">
        <span className="label">Filter</span>
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

      <div className="panel panel-pad">
        <UnitsChart rows={visible} />
      </div>

      <div className="panel">
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
                    <div className="cluster" style={{ gap: "var(--s-2)", flexWrap: "nowrap" }}>
                      <CompetitionMark competition={r.competition} size={22} />
                      <div style={{ minWidth: 0 }}>
                        <div className="cond" style={{ fontWeight: 600, whiteSpace: "nowrap" }}>
                          {r.home_team} <span style={{ color: "var(--ink-3)" }}>v</span> {r.away_team}
                        </div>
                        <div className="num" style={{ color: "var(--ink-3)", fontSize: "var(--t-micro)" }}>
                          {r.kickoff_at.slice(0, 10)}
                        </div>
                      </div>
                    </div>
                  </td>
                  <td>
                    {selectionLabel(r.selection, r.home_team, r.away_team, r.market)}
                    <div style={{ color: "var(--ink-3)", fontSize: "var(--t-micro)" }}>
                      {marketLabel(r.market)}
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
      </div>
    </>
  );
}

function Headline({ summary: s }: { summary: RecordSummary }) {
  const settledDecided = s.won + s.lost;
  return (
    <div className="stack-s">
      {/*
        One number at poster scale, and the rest at label scale beside it. A
        component library will give you four tiles of identical weight, which
        says every number matters the same amount. They do not: the return is
        the number someone came here for.
      */}
      <div
        className="panel panel-pad"
        style={{
          display: "flex",
          alignItems: "baseline",
          gap: "var(--s-5)",
          flexWrap: "wrap",
        }}
      >
        <div>
          <div className="label">Return, level stakes</div>
          <div
            className="mega num"
            style={{ color: s.roi_pct !== null && Number(s.roi_pct) > 0 ? "var(--brand)" : "var(--ink)" }}
          >
            {s.roi_pct === null ? (
              "held"
            ) : (
              <CountUp
                to={Number(s.roi_pct)}
                digits={1}
                prefix={Number(s.roi_pct) > 0 ? "+" : ""}
                suffix="%"
                duration={1100}
              />
            )}
          </div>
        </div>
        <div style={{ color: "var(--ink-3)", fontSize: "var(--t-small)", maxWidth: "34ch" }}>
          across{" "}
          <span className="cond num" style={{ color: "var(--ink)", fontWeight: 700 }}>
            {s.settled}
          </span>{" "}
          settled picks, staking one unit on every one of them, winners and
          losers alike. {Number(s.units).toFixed(2)} units.
        </div>
      </div>

      <div
        className="panel panel-pad"
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
          tone={s.hit_rate_pct !== null && Number(s.hit_rate_pct) >= 50 ? "won" : undefined}
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
          tone={s.roi_pct !== null && Number(s.roi_pct) > 0 ? "brand" : undefined}
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
