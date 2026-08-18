"use client";

import { MAX_LEGS, type Leg } from "./combo";
import type { Pick } from "./supabase";

/**
 * The in-progress combo lives in the browser, not in our database.
 *
 * A combo only becomes a `combo_sessions` row when the subscriber asks us to
 * save it. Until then there is nothing to store: we are not building a profile
 * of what someone browsed, and §12 gives us no reason to.
 */
const KEY = "gamesenze.combo";

export function readCombo(): Leg[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(KEY);
    return raw ? (JSON.parse(raw) as Leg[]) : [];
  } catch {
    return [];
  }
}

function write(legs: Leg[]): Leg[] {
  if (typeof window !== "undefined") {
    window.localStorage.setItem(KEY, JSON.stringify(legs));
  }
  return legs;
}

export function addToCombo(pick: Pick): Leg[] {
  const legs = readCombo();
  if (legs.some((l) => l.pickId === pick.id) || legs.length >= MAX_LEGS) {
    return legs;
  }
  const leg: Leg = {
    pickId: pick.id,
    fixtureId: pick.fixture_id,
    label: `${pick.home_team} v ${pick.away_team}`,
    market: pick.market,
    selection: pick.selection,
    odds: Number(pick.latest_odds ?? pick.capture_odds ?? 0),
    bookmaker: pick.latest_bookmaker ?? pick.capture_bookmaker ?? "unknown",
    oddsAsOf: pick.latest_odds_at ?? pick.published_at ?? new Date().toISOString(),
    sport: pick.sport,
  };
  return write([...legs, leg]);
}

export function removeFromCombo(pickId: string): Leg[] {
  return write(readCombo().filter((l) => l.pickId !== pickId));
}

export function clearCombo(): Leg[] {
  return write([]);
}
