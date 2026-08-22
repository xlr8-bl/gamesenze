"use client";

import { useEffect, useMemo, useState } from "react";
import { ArrowRight, Check, Plus } from "@phosphor-icons/react";
import {
  fetchBoard,
  fetchBudgetStatus,
  type BudgetStatus,
  type Pick,
} from "@/lib/supabase";
import { addToCombo, readCombo } from "@/lib/comboStorage";
import { MAX_LEGS } from "@/lib/combo";
import { Chip, Empty, Loading, Notice } from "@/components/ui";
import {
  ClubBadge,
  CompetitionHeader,
  Countdown,
  CrestWatermark,
  Drift,
  KickoffLine,
  PriceButton,
} from "@/components/sport";
import { confidenceLabel, factorLabel, splitRead, selectionLabel, marketLabel } from "@/lib/analysis";
import { competitionIdentity } from "@/lib/identity";
import { fixturePhoto } from "@/lib/media";

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
  const [comp, setComp] = useState("all");

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
  // the same view. The board is about what you can still act on.
  const open = useMemo(
    () =>
      (picks ?? [])
        .filter((p) => new Date(p.kickoff_at).getTime() > Date.now())
        .sort((a, b) => a.kickoff_at.localeCompare(b.kickoff_at)),
    [picks],
  );

  const competitions = useMemo(() => {
    const names = [...new Set(open.map((p) => p.competition ?? "Football"))];
    return names.sort(
      (a, b) => competitionIdentity(b).weight - competitionIdentity(a).weight,
    );
  }, [open]);

  const visible = comp === "all" ? open : open.filter((p) => (p.competition ?? "Football") === comp);

  // Grouped under branded headers, in competition-weight order, so a
  // Champions League night leads and a Tuesday in the Championship does not.
  const groups = useMemo(() => {
    const by = new Map<string, Pick[]>();
    for (const p of visible) {
      const k = p.competition ?? "Football";
      by.set(k, [...(by.get(k) ?? []), p]);
    }
    return [...by.entries()].sort(
      (a, b) => competitionIdentity(b[0]).weight - competitionIdentity(a[0]).weight,
    );
  }, [visible]);

  const banner = budget.map((b) => RUNG_BANNER[b.ladder_rung]).find((b) => b !== null);

  if (error) {
    return (
      <div className="shell stack" style={{ paddingTop: "var(--s-6)" }}>
        <Notice tone="bad">
          The board could not be loaded: {error}. This is our fault, not a quiet
          day. Nothing is missing below because it was withheld.
        </Notice>
      </div>
    );
  }

  if (picks === null) {
    return (
      <div className="shell" style={{ paddingTop: "var(--s-6)" }}>
        <Loading label="Loading the board" />
      </div>
    );
  }

  return (
    <div className="shell stack" style={{ paddingTop: "var(--s-6)" }}>
      <div className="row">
        <h1 className="poster" style={{ fontSize: "clamp(2rem, 1.5rem + 2.4vw, 3.25rem)" }}>
          Today&apos;s board
        </h1>
        <span className="cond" style={{ color: "var(--ink-3)", letterSpacing: "0.06em", textTransform: "uppercase" }}>
          <span className="num" style={{ color: "var(--brand)", fontWeight: 700 }}>{open.length}</span> open
        </span>
      </div>

      {banner && <Notice tone={banner.tone}>{banner.text}</Notice>}

      {competitions.length > 1 && (
        <div className="table-scroll" style={{ paddingBottom: 2 }}>
          <div className="seg" role="group" aria-label="Filter by competition">
            <button aria-pressed={comp === "all"} onClick={() => setComp("all")}>
              All
            </button>
            {competitions.map((c) => (
              <button key={c} aria-pressed={comp === c} onClick={() => setComp(c)}>
                {competitionIdentity(c).short}
              </button>
            ))}
          </div>
        </div>
      )}

      {open.length === 0 ? (
        <Empty title="Nothing open right now">
          A quiet board is a normal outcome, not an error. If today&apos;s data
          did not clear verification, we publish nothing rather than publish
          something we cannot stand behind. Picks that have already kicked off
          move to the <a href="/record/">record</a>, won or lost.
        </Empty>
      ) : (
        groups.map(([competition, rows]) => (
          <section key={competition} className="stack-s">
            <CompetitionHeader
              competition={competition}
              right={
                <span className="cond num" style={{ color: "var(--ink-2)", fontSize: "var(--t-small)", letterSpacing: "0.06em", whiteSpace: "nowrap" }}>
                  {rows.length} {rows.length === 1 ? "pick" : "picks"}
                </span>
              }
            />
            {rows.map((pick, i) => (
              <PickRow
                key={pick.id}
                pick={pick}
                index={i}
                added={inCombo.has(pick.id)}
                full={inCombo.size >= MAX_LEGS}
                onAdd={() => setInCombo(new Set(addToCombo(pick).map((l) => l.pickId)))}
              />
            ))}
          </section>
        ))
      )}

      {inCombo.size > 0 && <ComboTray count={inCombo.size} />}
    </div>
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
  const c = competitionIdentity(pick.competition);

  const read = splitRead(pick.reasoning_full);

  const disabled = added || full;
  const photo = fixturePhoto(pick.home_team, pick.away_team, index, c.key);

  return (
    <article
      className="panel rise"
      style={{ ["--i" as string]: index, overflow: "hidden" }}
      aria-labelledby={`pick-${pick.id}`}
    >
      {/* A hairline of the competition's colour along the top edge, so a card
          is placeable at a glance even out of its group. */}
      <div aria-hidden style={{ height: 3, background: `linear-gradient(90deg, ${c.accent}, transparent 70%)` }} />

      {/* The home side's crest at poster scale, bled off the right edge. It is
          decoration derived from the row's own data rather than applied to it,
          which is the only kind worth having. */}
      <CrestWatermark
        name={pick.home_team}
        size={260}
        style={{ right: -70, top: -40 }}
      />

      <div
        className={photo ? "photo photo-flat" : undefined}
        style={{
          padding: "var(--s-4)",
          minHeight: photo ? 108 : undefined,
          display: "flex",
          alignItems: "center",
        }}
      >
        {photo && <img src={photo} alt="" aria-hidden loading="lazy" decoding="async" />}
        <div className="row" style={{ alignItems: "center", gap: "var(--s-4)", width: "100%", position: "relative" }}>
          <div className="grow">
            <div className="cluster" style={{ gap: "var(--s-3)", flexWrap: "nowrap" }}>
              <div className="cluster" style={{ gap: 6, flexWrap: "nowrap" }}>
                <ClubBadge name={pick.home_team} size={40} />
                <ClubBadge name={pick.away_team} size={40} />
              </div>
              <div style={{ minWidth: 0 }}>
                <h2
                  id={`pick-${pick.id}`}
                  className="cond"
                  style={{ fontSize: "1.375rem", fontWeight: 700, letterSpacing: "0.01em", lineHeight: 1.12 }}
                >
                  {pick.home_team} <span style={{ color: "var(--ink-3)" }}>v</span> {pick.away_team}
                </h2>
                <KickoffLine at={pick.kickoff_at} />
              </div>
            </div>
          </div>
          <div style={{ textAlign: "right" }}>
            <div className="label" style={{ marginBottom: 1 }}>Kicks off in</div>
            <Countdown to={pick.kickoff_at} />
          </div>
        </div>
      </div>

      <div style={{ padding: "0 var(--s-4) var(--s-4)" }}>
        {/* The pick is the headline. Selection at poster scale on the left,
            the decision (confidence, price, value) on the right. Everything
            else on the card supports this line. */}
        <div className="pick-hero">
          <div>
            <div className="label">Our pick</div>
            <div
              className="cond"
              style={{
                fontWeight: 700,
                fontSize: "clamp(1.75rem, 1.2rem + 2vw, 2.5rem)",
                lineHeight: 1.02,
                letterSpacing: "-0.01em",
                textTransform: "uppercase",
              }}
            >
              {selectionLabel(pick.selection, pick.home_team, pick.away_team, pick.market)}
            </div>
            <div className="cond" style={{ color: "var(--ink-3)", fontSize: "1rem", letterSpacing: "0.03em", textTransform: "uppercase" }}>
              {marketLabel(pick.market)}
            </div>
          </div>

          <div className="pick-decision">
            {pick.confidence_tag && (
              <span
                className={pick.confidence_tag === "best_bet" ? "chip chip-brand" : "chip chip-outline-brand"}
                style={{ fontSize: "var(--t-small)", padding: "5px var(--s-3)" }}
              >
                {confidenceLabel(pick.confidence_tag)}
              </span>
            )}
            <div style={{ textAlign: "center" }}>
              <PriceButton
                odds={odds}
                book={book}
                selected={added}
                disabled={disabled}
                onClick={onAdd}
                label={`${added ? "Remove" : "Add"} ${selectionLabel(pick.selection, pick.home_team, pick.away_team, pick.market)} at ${odds?.toFixed(2)} ${added ? "from" : "to"} your combo`}
              />
              <div style={{ marginTop: 5, minHeight: 14 }}>
                <Drift from={pick.capture_odds} to={pick.latest_odds} />
              </div>
            </div>
          </div>
        </div>

        {/* The pick sits above; the analysis reads underneath it in plain
            football language, the way a tipsheet lays out a call. */}
        {read.lead && (
          <div style={{ marginTop: "var(--s-5)" }}>
            <div className="label" style={{ color: "var(--brand)", marginBottom: 6 }}>Our analysis</div>
            <p
              style={{
                fontSize: "1.0625rem",
                lineHeight: 1.4,
                color: "var(--ink)",
                fontWeight: 500,
                marginBottom: read.body ? "var(--s-2)" : 0,
              }}
            >
              {read.lead}
            </p>
            {read.body && (
              <p style={{ color: "var(--ink-2)", fontSize: "var(--t-small)", marginBottom: 0 }}>
                {read.body}
              </p>
            )}
          </div>
        )}

        {/*
          The honesty stays but stops being a statistics callout: one plain
          line, muted, no jargon and no thresholds. We don't hide what we left
          out; we don't lecture about it either.
        */}
        {excluded.length > 0 && (
          <p style={{ color: "var(--ink-3)", fontSize: "var(--t-small)", marginTop: "var(--s-3)", marginBottom: 0 }}>
            Left out this early in the season:{" "}
            {excluded.map((f) => factorLabel(f.factor).toLowerCase()).join(", ")}.
          </p>
        )}

        <div
          className="row"
          style={{
            marginTop: "var(--s-4)",
            paddingTop: "var(--s-3)",
            borderTop: "1px solid var(--line)",
            color: "var(--ink-3)",
            fontSize: "var(--t-micro)",
          }}
        >
          <span>
            Price read{" "}
            <span className="num">
              {captured ? new Date(captured).toISOString().slice(11, 16) : "unknown"}
            </span>{" "}
            UTC. Not a live quote; confirm at your book.
          </span>
          <span className="cluster" style={{ gap: 5, color: added ? "var(--brand)" : "var(--ink-3)" }}>
            {added ? <Check size={12} weight="bold" aria-hidden /> : <Plus size={12} weight="bold" aria-hidden />}
            {added ? "In your combo" : full ? `Combo full at ${MAX_LEGS}` : "Tap the price to add"}
          </span>
        </div>
      </div>
    </article>
  );
}

function ComboTray({ count }: { count: number }) {
  return (
    <div
      className="panel panel-hi rise"
      style={{
        position: "sticky",
        bottom: "var(--s-4)",
        zIndex: 200,
        padding: "var(--s-3) var(--s-4)",
      }}
    >
      <div className="row" style={{ flexWrap: "nowrap" }}>
        <span className="cond" style={{ letterSpacing: "0.05em", textTransform: "uppercase", fontWeight: 600 }}>
          <span className="num" style={{ color: "var(--brand)", fontWeight: 700 }}>{count}</span> of {MAX_LEGS} legs
        </span>
        <a href="/combo-builder/" className="btn btn-sm">
          Open combo
          <ArrowRight size={14} weight="bold" aria-hidden />
        </a>
      </div>
    </div>
  );
}
