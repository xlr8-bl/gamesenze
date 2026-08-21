"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { Check, Copy, Trash, X } from "@phosphor-icons/react";
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
import { Empty, Notice, Stat } from "@/components/ui";

const STAKES = [10, 25, 50, 100];

export default function ComboBuilder() {
  const [legs, setLegs] = useState<Leg[] | null>(null);
  const [stake, setStake] = useState(100);
  const [record, setRecord] = useState<{ settled: number; won: number } | null>(
    null,
  );

  useEffect(() => setLegs(readCombo()), []);

  const quote = useMemo(() => buildQuote(legs ?? [], stake), [legs, stake]);
  const legCount = legs?.length ?? 0;
  const enough = legCount >= MIN_LEGS;

  useEffect(() => {
    if (!enough || !isConfigured) return;
    let live = true;
    getSupabase()
      .from("v_combo_performance")
      .select("leg_count, settled_bets, won")
      .eq("leg_count", legCount)
      .maybeSingle()
      .then(({ data }) => {
        if (live && data) {
          setRecord({
            settled: Number(data.settled_bets ?? 0),
            won: Number(data.won ?? 0),
          });
        }
      });
    return () => {
      live = false;
    };
  }, [legCount, enough]);

  if (legs === null) return null;

  if (legs.length === 0) {
    return (
      <main className="stack">
        <h1>Combo builder</h1>
        <Empty title="No picks selected">
          Add between {MIN_LEGS} and {MAX_LEGS} picks from the{" "}
          <a href="/board/">board</a> and the combined maths appears here. The
          selection lives in this browser only; nothing is sent to us until you
          choose to save a combo.
        </Empty>
      </main>
    );
  }

  return (
    <main className="stack">
      <div className="row">
        <h1>Combo builder</h1>
        <span style={{ color: "var(--ink-3)", fontSize: "var(--t-small)" }}>
          <span className="num">{legs.length}</span> of {MAX_LEGS} legs
        </span>
      </div>

      <section className="panel panel-flush">
        <div className="ledger">
          {legs.map((leg) => (
            <div key={leg.pickId} className="ledger-row row" style={{ gap: "var(--s-3)" }}>
              <div style={{ minWidth: 0 }}>
                <div style={{ fontWeight: 550 }}>{leg.label}</div>
                <div style={{ color: "var(--ink-3)", fontSize: "var(--t-small)" }}>
                  {leg.selection} in {leg.market}, at {leg.bookmaker}
                </div>
              </div>
              <div className="cluster" style={{ gap: "var(--s-4)", flexWrap: "nowrap" }}>
                <span className="num" style={{ fontSize: "1.0625rem" }}>
                  {leg.odds.toFixed(2)}
                </span>
                <button
                  className="btn btn-quiet btn-sm"
                  onClick={() => setLegs(removeFromCombo(leg.pickId))}
                  aria-label={`Remove ${leg.label} from the combo`}
                >
                  <X size={14} weight="bold" aria-hidden />
                </button>
              </div>
            </div>
          ))}
        </div>
        <p
          className="p-full"
          style={{
            padding: "var(--s-3) var(--s-5)",
            borderTop: "1px solid var(--line)",
            color: "var(--ink-3)",
            fontSize: "var(--t-micro)",
            margin: 0,
          }}
        >
          Prices as of {formatUtc(quote.oddsAsOf)}, the oldest capture among
          these legs. Not a live quote; confirm at your book before staking.
        </p>
      </section>

      {!enough ? (
        <Notice>
          A combo needs at least {MIN_LEGS} legs. Add another from the{" "}
          <a href="/board/">board</a>.
        </Notice>
      ) : (
        <>
          <section className="panel stack-s">
            <div
              style={{
                display: "grid",
                gap: "var(--s-5)",
                gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))",
              }}
            >
              <Stat label="Combined price" value={quote.totalOdds.toFixed(2)} size="xl" />
              <Stat
                label={`£${stake} returns`}
                value={`£${quote.payout.toFixed(2)}`}
                note={`£${quote.profit.toFixed(2)} profit`}
                size="xl"
              />
              <Stat
                label="Price implies"
                value={`${(quote.impliedProb * 100).toFixed(1)}%`}
                note="chance of landing"
                size="xl"
              />
            </div>
            <div
              className="seg"
              role="group"
              aria-label="Stake"
              style={{ alignSelf: "flex-start", marginTop: "var(--s-2)" }}
            >
              {STAKES.map((s) => (
                <button key={s} aria-pressed={s === stake} onClick={() => setStake(s)}>
                  £{s}
                </button>
              ))}
            </div>
          </section>

          {/*
            Independence is an assumption, not a fact. Where it does not hold we
            say so rather than quote a confident number we cannot defend.
          */}
          {quote.warnings.map((warning) => (
            <Notice tone="caution" key={warning}>
              {warning}
            </Notice>
          ))}

          <RiskNote
            legCount={legs.length}
            impliedProb={quote.impliedProb}
            record={record}
          />

          <Slip legs={legs} totalOdds={quote.totalOdds} />

          <button className="btn btn-ghost self-start" onClick={() => setLegs(clearCombo())}>
            <Trash size={14} weight="bold" aria-hidden />
            Clear combo
          </button>
        </>
      )}
    </main>
  );
}

/**
 * The slip, ready to be copied into someone else's bet slip.
 *
 * Copying is a reversible action with an obvious result, so it confirms itself
 * in place and reverts, rather than opening anything.
 */
function Slip({ legs, totalOdds }: { legs: Leg[]; totalOdds: number }) {
  const [copied, setCopied] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => () => {
    if (timer.current) clearTimeout(timer.current);
  }, []);

  const text = [
    ...legs.map(
      (l) =>
        `${l.label}: ${l.selection} in ${l.market} at ${l.odds.toFixed(2)} (${l.bookmaker})`,
    ),
    "",
    `Combined: ${totalOdds.toFixed(2)}`,
  ].join("\n");

  async function copy() {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      if (timer.current) clearTimeout(timer.current);
      timer.current = setTimeout(() => setCopied(false), 2000);
    } catch {
      setCopied(false);
    }
  }

  return (
    <section className="panel stack-s">
      <div className="row">
        <h2>Place this at your book</h2>
        <button className="btn btn-ghost btn-sm" onClick={copy}>
          {copied ? (
            <>
              <Check size={13} weight="bold" aria-hidden /> Copied
            </>
          ) : (
            <>
              <Copy size={13} weight="bold" aria-hidden /> Copy slip
            </>
          )}
        </button>
      </div>
      <pre
        style={{
          margin: 0,
          padding: "var(--s-3)",
          background: "var(--bg)",
          border: "1px solid var(--line)",
          borderRadius: "var(--r-2)",
          whiteSpace: "pre-wrap",
          fontFamily: "var(--mono)",
          fontSize: "var(--t-small)",
          color: "var(--ink-2)",
          overflowX: "auto",
        }}
      >
        {text}
      </pre>
      <p style={{ color: "var(--ink-3)", fontSize: "var(--t-small)", margin: 0 }}>
        {DISCLAIMER} We send nothing to any sportsbook and earn nothing from
        your stake.
      </p>
      <span role="status" aria-live="polite" className="sr-only">
        {copied ? "Slip copied to the clipboard" : ""}
      </span>
    </section>
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
  // number a reader would reasonably treat as meaningful.
  if (!record || record.settled < 20) {
    return (
      <Notice>
        {legCount}-leg combos: too few have settled in our record to quote a hit
        rate yet. All we can tell you is what the price says, which is{" "}
        {(impliedProb * 100).toFixed(1)}%.
      </Notice>
    );
  }
  const observed = (record.won / record.settled) * 100;
  const implied = impliedProb * 100;
  return (
    <Notice tone={observed < implied ? "caution" : "neutral"}>
      {legCount}-leg combos have landed {observed.toFixed(1)}% of the time in
      our record ({record.won} of {record.settled}). This one&apos;s price
      implies {implied.toFixed(1)}%.
    </Notice>
  );
}
