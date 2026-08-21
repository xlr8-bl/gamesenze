"use client";

import { useEffect, useState } from "react";
import { ArrowUpRight, Check, Plus } from "@phosphor-icons/react";
import {
  fetchBoard,
  fetchBudgetStatus,
  type BudgetStatus,
  type Pick,
} from "@/lib/supabase";
import { addToCombo, readCombo } from "@/lib/comboStorage";
import { MAX_LEGS } from "@/lib/combo";
import { Empty, Loading, Notice, Tag } from "@/components/ui";

const RUNG_BANNER: Record<
  BudgetStatus["ladder_rung"],
  { tone: "caution" | "bad"; text: string } | null
> = {
  normal: null,
  reduced: {
    tone: "caution",
    text: "Reduced odds cadence. Prices outside the final three hours before kickoff are updating half as often today.",
  },
  closing_only: {
    tone: "caution",
    text: "Closing prices only. Intermediate odds updates are paused for the rest of this period; what you see below is the last capture.",
  },
  exhausted: {
    tone: "bad",
    text: "Request budget reached for this period. Prices below are last-known, with the time they were captured, and no new picks are publishing.",
  },
};

export default function Board() {
  const [picks, setPicks] = useState<Pick[] | null>(null);
  const [budget, setBudget] = useState<BudgetStatus[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [inCombo, setInCombo] = useState<Set<string>>(new Set());

  useEffect(() => {
    let live = true;
    Promise.all([fetchBoard(), fetchBudgetStatus()])
      .then(([board, status]) => {
        if (!live) return;
        setPicks(board);
        setBudget(status);
      })
      .catch((e) => live && setError(String(e?.message ?? e)));
    setInCombo(new Set(readCombo().map((l) => l.pickId)));
    return () => {
      live = false;
    };
  }, []);

  // v_published_picks carries settled picks too, so the record page can read
  // the same view. The board is about what you can still act on, so anything
  // already kicked off is filtered out here rather than shown with an empty
  // result column. It has not disappeared: it is on the record page.
  const open = (picks ?? []).filter(
    (p) => new Date(p.kickoff_at).getTime() > Date.now(),
  );

  // Degradation is never silent. The worst rung across providers is the one
  // the reader needs to know about, so it is the one that renders.
  const banner = budget
    .map((b) => RUNG_BANNER[b.ladder_rung])
    .find((b) => b !== null);

  if (error) {
    return (
      <main className="stack">
        <Notice tone="bad">
          The board could not be loaded: {error}. This is our fault, not a quiet
          day. Nothing below is missing because it was withheld.
        </Notice>
      </main>
    );
  }

  if (picks === null) return <Loading label="Loading the board" />;

  return (
    <main className="stack">
      <div className="row">
        <h1>Board</h1>
        <span style={{ color: "var(--ink-3)", fontSize: "var(--t-small)" }}>
          <span className="num">{open.length}</span> open
        </span>
      </div>

      {banner && <Notice tone={banner.tone}>{banner.text}</Notice>}

      {open.length === 0 ? (
        <Empty title="Nothing open right now">
          A quiet board is a normal outcome, not an error. If today&apos;s data
          did not clear verification, we publish nothing rather than publish
          something we cannot stand behind. Picks that have already kicked off
          move to the <a href="/record/">record</a>, won or lost.
        </Empty>
      ) : (
        <div className="stack">
          {open.map((pick, i) => (
            <PickRow
              key={pick.id}
              pick={pick}
              index={i}
              added={inCombo.has(pick.id)}
              full={inCombo.size >= MAX_LEGS}
              onAdd={() =>
                setInCombo(new Set(addToCombo(pick).map((l) => l.pickId)))
              }
            />
          ))}
        </div>
      )}

      {inCombo.size > 0 && <ComboTray count={inCombo.size} />}
    </main>
  );
}

function PickRow({
  pick,
  index,
  added,
  full,
  onAdd,
}: {
  pick: Pick;
  index: number;
  added: boolean;
  full: boolean;
  onAdd: () => void;
}) {
  const odds = pick.latest_odds ?? pick.capture_odds;
  const excluded = pick.excluded_factors ?? [];
  const book = pick.latest_bookmaker ?? pick.capture_bookmaker;
  const captured = pick.latest_odds_at ?? pick.published_at;

  // Our number against the market's. The gap is the entire reason the pick
  // exists, so it is shown rather than described.
  const implied = odds ? 1 / odds : null;
  const edge =
    pick.internal_prob !== null && implied !== null
      ? (pick.internal_prob - implied) * 100
      : null;

  const kickoff = new Date(pick.kickoff_at);
  const disabled = added || full;

  return (
    <article
      className="panel enter"
      style={{ ["--i" as string]: index }}
      aria-labelledby={`pick-${pick.id}`}
    >
      <div className="row" style={{ alignItems: "flex-start" }}>
        <div>
          <h2 id={`pick-${pick.id}`}>
            {pick.home_team} v {pick.away_team}
          </h2>
          <div
            className="cluster"
            style={{
              color: "var(--ink-3)",
              fontSize: "var(--t-small)",
              marginTop: 2,
              gap: "var(--s-3)",
            }}
          >
            <span>
              {kickoff.toLocaleDateString("en-GB", {
                weekday: "short",
                day: "numeric",
                month: "short",
                timeZone: "UTC",
              })}
            </span>
            <span className="num">
              {kickoff.toISOString().slice(11, 16)} UTC
            </span>
          </div>
        </div>
        <button
          className={`btn ${added ? "btn-quiet" : "btn-ghost"} btn-sm`}
          onClick={onAdd}
          disabled={disabled}
          aria-disabled={disabled}
          title={
            added
              ? "Already in your combo"
              : full
                ? `A combo holds at most ${MAX_LEGS} legs`
                : undefined
          }
        >
          {added ? (
            <>
              <Check size={13} weight="bold" aria-hidden /> In combo
            </>
          ) : (
            <>
              <Plus size={13} weight="bold" aria-hidden /> Add to combo
            </>
          )}
        </button>
      </div>

      {/* The selection and its price, given the weight they deserve. */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))",
          gap: "var(--s-4)",
          margin: "var(--s-4) 0",
          paddingTop: "var(--s-4)",
          borderTop: "1px solid var(--line)",
        }}
      >
        <div style={{ gridColumn: "span 2", minWidth: 0 }}>
          <div style={{ color: "var(--ink-3)", fontSize: "var(--t-small)" }}>
            Selection
          </div>
          <div style={{ fontWeight: 550, marginTop: 2 }}>
            {pick.selection}
            <span style={{ color: "var(--ink-3)", fontWeight: 400 }}>
              {" "}
              in {pick.market}
            </span>
          </div>
        </div>
        <div>
          <div style={{ color: "var(--ink-3)", fontSize: "var(--t-small)" }}>
            Best price
          </div>
          <div className="num num-lg">{odds ? odds.toFixed(2) : "none"}</div>
          <div style={{ color: "var(--ink-3)", fontSize: "var(--t-micro)" }}>
            {book ?? "no book"}
          </div>
        </div>
        <div>
          <div style={{ color: "var(--ink-3)", fontSize: "var(--t-small)" }}>
            Our number
          </div>
          <div className="num num-lg">
            {pick.internal_prob !== null
              ? `${(pick.internal_prob * 100).toFixed(1)}%`
              : "held"}
          </div>
          <div style={{ color: "var(--ink-3)", fontSize: "var(--t-micro)" }}>
            {implied !== null
              ? `price implies ${(implied * 100).toFixed(1)}%`
              : "no price"}
          </div>
        </div>
      </div>

      {edge !== null && <EdgeBar edge={edge} />}

      {(pick.confidence_tag || (pick.stakes_tags ?? []).length > 0) && (
        <div className="cluster" style={{ marginBottom: "var(--s-3)" }}>
          {pick.confidence_tag && (
            <Tag strong>{pick.confidence_tag.replace(/_/g, " ")}</Tag>
          )}
          {(pick.stakes_tags ?? []).map((tag) => (
            <Tag key={tag}>{tag.replace(/_/g, " ")}</Tag>
          ))}
        </div>
      )}

      {pick.reasoning_full && (
        <p style={{ color: "var(--ink-2)" }}>{pick.reasoning_full}</p>
      )}

      {/*
        REQ-QA-2: a factor we could not use renders as an explicit block.
        Stating the limit is a trust asset; hiding it is the beginning of a
        track record we cannot defend.
      */}
      {excluded.length > 0 && (
        <div className="stack-s" style={{ marginTop: "var(--s-4)" }}>
          {excluded.map((factor) => (
            <Notice tone="caution" key={factor.factor}>
              {factor.message}
            </Notice>
          ))}
        </div>
      )}

      <div
        style={{
          marginTop: "var(--s-4)",
          paddingTop: "var(--s-3)",
          borderTop: "1px solid var(--line)",
          color: "var(--ink-3)",
          fontSize: "var(--t-micro)",
        }}
      >
        Price captured{" "}
        <span className="num">
          {captured ? new Date(captured).toISOString().slice(11, 16) : "unknown"}
        </span>{" "}
        UTC. Not a live quote; confirm at your book before staking.
      </div>
    </article>
  );
}

/**
 * The edge, drawn to scale.
 *
 * A bar chart of one value, on a fixed domain of plus or minus 15 points, so
 * two picks on different days are directly comparable. The scale is fixed
 * deliberately: a bar that always fills the width would make every edge look
 * the same size.
 */
function EdgeBar({ edge }: { edge: number }) {
  const DOMAIN = 15;
  const pct = Math.min(Math.abs(edge), DOMAIN) / DOMAIN;
  const positive = edge >= 0;
  return (
    <div style={{ marginBottom: "var(--s-4)" }}>
      <div
        className="row"
        style={{ marginBottom: 6, gap: "var(--s-2)", flexWrap: "nowrap" }}
      >
        <span style={{ color: "var(--ink-3)", fontSize: "var(--t-small)" }}>
          Edge over the market
        </span>
        <span
          className={`num ${positive ? "sign-pos" : "sign-neg"}`}
          style={{ fontSize: "var(--t-small)" }}
        >
          {positive ? "+" : ""}
          {edge.toFixed(1)} pts
        </span>
      </div>
      <div
        style={{ display: "flex", height: 6, gap: 2, position: "relative" }}
        role="img"
        aria-label={`Edge over the market: ${edge.toFixed(1)} percentage points, on a scale of plus or minus ${DOMAIN}`}
      >
        {/* Left half runs right-to-left from the centre, so the zero line is
            the middle of the track and the direction reads without a label. */}
        <div
          style={{
            flex: 1,
            display: "flex",
            justifyContent: "flex-end",
            background: "var(--line)",
            borderRadius: "var(--r-1) 0 0 var(--r-1)",
          }}
        >
          {!positive && (
            <span
              style={{
                width: `${pct * 100}%`,
                background: "var(--lost)",
                borderRadius: "var(--r-1) 0 0 var(--r-1)",
              }}
            />
          )}
        </div>
        {/* The zero mark. Without it a centre-anchored bar is unreadable. */}
        <span
          aria-hidden
          style={{
            position: "absolute",
            left: "50%",
            top: -3,
            width: 1,
            height: 12,
            marginLeft: -0.5,
            background: "var(--line-firm)",
          }}
        />
        <div
          style={{
            flex: 1,
            background: "var(--line)",
            borderRadius: "0 var(--r-1) var(--r-1) 0",
          }}
        >
          {positive && (
            <span
              style={{
                display: "block",
                height: "100%",
                width: `${pct * 100}%`,
                background: "var(--won)",
                borderRadius: "0 var(--r-1) var(--r-1) 0",
              }}
            />
          )}
        </div>
      </div>
    </div>
  );
}

/** Sticky only once there is something in it. */
function ComboTray({ count }: { count: number }) {
  return (
    <div
      className="panel enter"
      style={{
        position: "sticky",
        bottom: "var(--s-4)",
        zIndex: "var(--z-tray)" as unknown as number,
        padding: "var(--s-3) var(--s-4)",
        background: "var(--raised)",
        borderColor: "var(--line-firm)",
      }}
    >
      <div className="row" style={{ flexWrap: "nowrap" }}>
        <span style={{ fontSize: "var(--t-small)" }}>
          <span className="num">{count}</span> of {MAX_LEGS} legs selected
        </span>
        <a href="/combo-builder/" className="btn btn-sm">
          Open combo builder
          <ArrowUpRight size={13} weight="bold" aria-hidden />
        </a>
      </div>
    </div>
  );
}
