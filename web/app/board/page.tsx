"use client";

import { useEffect, useState } from "react";
import {
  fetchBoard,
  fetchBudgetStatus,
  type BudgetStatus,
  type Pick,
} from "@/lib/supabase";
import { formatUtc } from "@/lib/combo";
import { addToCombo, readCombo } from "@/lib/comboStorage";

const RUNG_BANNER: Record<BudgetStatus["ladder_rung"], string | null> = {
  normal: null,
  reduced:
    "Reduced odds cadence — prices outside the final three hours are updating half as often today.",
  closing_only:
    "Closing prices only — intermediate odds updates are paused for the rest of this period.",
  exhausted:
    "Request budget reached. Prices below are last-known, with the time they were captured. No new picks are being published.",
};

export default function Board() {
  const [picks, setPicks] = useState<Pick[]>([]);
  const [budget, setBudget] = useState<BudgetStatus[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [comboSize, setComboSize] = useState(0);

  useEffect(() => {
    Promise.all([fetchBoard(), fetchBudgetStatus()])
      .then(([board, status]) => {
        setPicks(board);
        setBudget(status);
      })
      .catch((e) => setError(String(e?.message ?? e)));
    setComboSize(readCombo().length);
  }, []);

  // §8: degradation is never silent. The worst rung across providers is the
  // one the reader needs to know about.
  const banner = budget
    .map((b) => RUNG_BANNER[b.ladder_rung])
    .find((b) => b !== null);

  if (error) {
    return (
      <main>
        <div className="warning">Could not load the board: {error}</div>
      </main>
    );
  }

  return (
    <main>
      {banner && <div className="banner">{banner}</div>}

      {picks.length === 0 && (
        <div className="card">
          <h3>Nothing published right now</h3>
          <p className="meta">
            A quiet board is a normal outcome, not an error. If today&apos;s
            data did not pass verification, we publish nothing rather than
            publish something we cannot stand behind.
          </p>
        </div>
      )}

      {picks.map((pick) => (
        <PickCard
          key={pick.id}
          pick={pick}
          onAdd={() => setComboSize(addToCombo(pick).length)}
        />
      ))}

      {comboSize > 0 && (
        <div className="card">
          <div className="row">
            <span>
              {comboSize} pick{comboSize === 1 ? "" : "s"} in your combo
            </span>
            <a href="/combo-builder/">
              <button>Open combo builder</button>
            </a>
          </div>
        </div>
      )}
    </main>
  );
}

function PickCard({ pick, onAdd }: { pick: Pick; onAdd: () => void }) {
  const odds = pick.latest_odds ?? pick.capture_odds;
  const excluded = pick.excluded_factors ?? [];

  return (
    <article className="card">
      <div className="row">
        <div>
          <h3>
            {pick.home_team} v {pick.away_team}
          </h3>
          <div className="meta">
            {new Date(pick.kickoff_at).toUTCString()} · {pick.sport}
          </div>
        </div>
        <button className="ghost" onClick={onAdd}>
          Add to combo
        </button>
      </div>

      <p style={{ margin: "12px 0 4px" }}>
        <strong>
          {pick.market} · {pick.selection}
        </strong>{" "}
        <span className="num">@ {odds?.toFixed(2) ?? "—"}</span>{" "}
        <span className="meta">
          {pick.latest_bookmaker ?? pick.capture_bookmaker} · as of{" "}
          {formatUtc(pick.latest_odds_at)}
        </span>
      </p>

      <div>
        {pick.confidence_tag && (
          <span className="pill">{pick.confidence_tag.replace("_", " ")}</span>
        )}
        {(pick.stakes_tags ?? []).map((tag) => (
          <span className="pill" key={tag}>
            {tag.replace(/_/g, " ")}
          </span>
        ))}
      </div>

      {pick.reasoning_full && (
        <p style={{ marginBottom: 0 }}>{pick.reasoning_full}</p>
      )}

      {/*
        REQ-QA-2: an excluded factor renders as an explicit data-limit block.
        Stating the limit is a trust asset; hiding it is the beginning of a
        track record we cannot defend.
      */}
      {excluded.map((factor) => (
        <p className="limit" key={factor.factor}>
          {factor.message}
        </p>
      ))}
    </article>
  );
}
