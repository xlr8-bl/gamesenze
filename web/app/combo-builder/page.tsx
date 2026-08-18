"use client";

import { useEffect, useMemo, useState } from "react";
import {
  DISCLAIMER,
  MAX_LEGS,
  MIN_LEGS,
  buildQuote,
  formatUtc,
  type Leg,
} from "@/lib/combo";
import { clearCombo, readCombo, removeFromCombo } from "@/lib/comboStorage";
import { getSupabase, isConfigured } from "@/lib/supabase";

const STAKES = [10, 25, 50, 100];

export default function ComboBuilder() {
  const [legs, setLegs] = useState<Leg[]>([]);
  const [stake, setStake] = useState(100);
  const [trackRecord, setTrackRecord] = useState<{
    settled: number;
    won: number;
  } | null>(null);

  useEffect(() => setLegs(readCombo()), []);

  const quote = useMemo(() => buildQuote(legs, stake), [legs, stake]);
  const enoughLegs = legs.length >= MIN_LEGS;

  useEffect(() => {
    if (!enoughLegs || !isConfigured) return;
    getSupabase()
      .from("v_combo_performance")
      .select("leg_count, settled_bets, won")
      .eq("leg_count", legs.length)
      .maybeSingle()
      .then(({ data }) => {
        if (data) {
          setTrackRecord({
            settled: Number(data.settled_bets ?? 0),
            won: Number(data.won ?? 0),
          });
        }
      });
  }, [legs.length, enoughLegs]);

  if (legs.length === 0) {
    return (
      <main>
        <div className="card">
          <h3>No picks selected</h3>
          <p className="meta">
            Add between {MIN_LEGS} and {MAX_LEGS} picks from the{" "}
            <a href="/board/">board</a> to see the combined maths.
          </p>
        </div>
      </main>
    );
  }

  return (
    <main>
      <div className="card">
        <h3>Your legs</h3>
        <table>
          <thead>
            <tr>
              <th>Pick</th>
              <th>Market</th>
              <th>Book</th>
              <th className="num">Odds</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {legs.map((leg) => (
              <tr key={leg.pickId}>
                <td>{leg.label}</td>
                <td>
                  {leg.market} {leg.selection}
                </td>
                <td>{leg.bookmaker}</td>
                <td className="num">{leg.odds.toFixed(2)}</td>
                <td>
                  <button
                    className="ghost"
                    onClick={() => setLegs(removeFromCombo(leg.pickId))}
                  >
                    Remove
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="meta" style={{ marginBottom: 0 }}>
          Prices as of {formatUtc(quote.oddsAsOf)} — the oldest capture among
          these legs. Not a live quote; confirm at your book before staking.
        </p>
      </div>

      {!enoughLegs && (
        <div className="warning">
          A combo needs at least {MIN_LEGS} legs. Add another from the board.
        </div>
      )}

      {enoughLegs && (
        <>
          <div className="card">
            <div className="row">
              <div>
                <div className="meta">Combined price</div>
                <div className="big num">{quote.totalOdds.toFixed(2)}</div>
              </div>
              <div>
                <div className="meta">£{stake} returns</div>
                <div className="big num">£{quote.payout.toFixed(2)}</div>
                <div className="meta num">
                  profit £{quote.profit.toFixed(2)}
                </div>
              </div>
              <div>
                <div className="meta">Price implies</div>
                <div className="big num">
                  {(quote.impliedProb * 100).toFixed(1)}%
                </div>
              </div>
            </div>

            <div style={{ marginTop: 14 }}>
              {STAKES.map((s) => (
                <button
                  key={s}
                  className={s === stake ? "" : "ghost"}
                  style={{ marginRight: 8 }}
                  onClick={() => setStake(s)}
                >
                  £{s}
                </button>
              ))}
            </div>
          </div>

          {/*
            Independence is an assumption, not a fact. Where it does not hold we
            say so rather than quote a confident number we cannot defend.
          */}
          {quote.warnings.map((warning) => (
            <div className="warning" key={warning}>
              {warning}
            </div>
          ))}

          <RiskNote
            legCount={legs.length}
            impliedProb={quote.impliedProb}
            record={trackRecord}
          />

          <div className="card">
            <h3>Place this at your book</h3>
            <pre
              style={{
                whiteSpace: "pre-wrap",
                margin: 0,
                fontSize: 13,
                color: "var(--muted)",
              }}
            >
              {legs
                .map(
                  (l) =>
                    `${l.label} — ${l.market} ${l.selection} @ ${l.odds.toFixed(
                      2,
                    )} (${l.bookmaker})`,
                )
                .join("\n")}
              {`\n\nCombined: ${quote.totalOdds.toFixed(2)}`}
            </pre>
            <p className="meta" style={{ marginTop: 12, marginBottom: 0 }}>
              {DISCLAIMER} Copy the details above into your own bet slip — we
              send nothing to any sportsbook and earn nothing from your stake.
            </p>
          </div>

          <button className="ghost" onClick={() => setLegs(clearCombo())}>
            Clear combo
          </button>
        </>
      )}
    </main>
  );
}

function RiskNote({
  legCount,
  impliedProb,
  record,
}: {
  legCount: number;
  impliedProb: number;
  record: { settled: number; won: number } | null;
}) {
  // Below 20 settled bets we decline to quote a rate rather than present a
  // number that a reader would reasonably treat as meaningful.
  if (!record || record.settled < 20) {
    return (
      <div className="limit">
        {legCount}-leg combos: too few settled in our record so far to quote a
        hit rate. The price implies {(impliedProb * 100).toFixed(1)}%.
      </div>
    );
  }
  const observed = record.won / record.settled;
  return (
    <div className="limit">
      {legCount}-leg combos have landed {(observed * 100).toFixed(1)}% of the
      time in our record ({record.won}/{record.settled}); this one&apos;s price
      implies {(impliedProb * 100).toFixed(1)}%.
    </div>
  );
}
