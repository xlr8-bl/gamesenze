/**
 * Presentation helpers for the analytical layer.
 *
 * The commercial line this draws: a subscriber should see *what* we concluded
 * and *how confident* we are, never the calibrated probability the model
 * produced or the exact rule that gated a factor. Those are the parts a
 * competitor would copy, and they are the parts these helpers keep off the
 * page. Everything a reader does see is either the verdict, its confidence, or
 * a value band, none of which reconstruct the method.
 */

/** Confidence, in the language a reader uses rather than the enum we store. */
export function confidenceLabel(tag: string | null): string {
  switch (tag) {
    case "best_bet":
      return "Best bet";
    case "strong_lean":
      return "Strong lean";
    case "lean":
      return "Lean";
    default:
      return "On the board";
  }
}

/**
 * A value band from the edge, never the edge itself.
 *
 * The raw edge is our probability minus the market's, so printing it to a
 * decimal hands a reader the model's number by subtraction. The band is the
 * commercial signal without the arithmetic: it says the price is wrong in our
 * favour and roughly how wrong, and stops there.
 */
export type ValueBand = { label: string; pips: number };

export function valueBand(edge: number | null): ValueBand | null {
  if (edge === null || edge <= 0) return null;
  if (edge >= 6) return { label: "Prime value", pips: 4 };
  if (edge >= 3.5) return { label: "Strong value", pips: 3 };
  if (edge >= 1.5) return { label: "Clear value", pips: 2 };
  return { label: "Slight edge", pips: 1 };
}

/**
 * The signals that fed a pick, named for a reader.
 *
 * Listing which angles we read is a depth signal; publishing how they were
 * weighted would be the method. These labels do the first and not the second.
 * An unknown slug is title-cased rather than dropped, so a new factor still
 * renders as words.
 */
const FACTOR_LABELS: Record<string, string> = {
  xg_form: "Expected-goals form",
  defensive_pressure: "Defensive pressure",
  home_form: "Home form",
  away_form: "Away form",
  rest_advantage: "Rest advantage",
  pace: "Match tempo",
  both_press: "Both sides press",
  low_variance: "Low-variance profile",
  set_pieces: "Set-piece threat",
  finishing: "Finishing quality",
  schedule: "Fixture congestion",
  head_to_head: "Head-to-head",
  prior_season: "Last season's baseline",
};

export function factorLabel(slug: string): string {
  return (
    FACTOR_LABELS[slug] ??
    slug
      .split("_")
      .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
      .join(" ")
  );
}

/**
 * Split a written read into a verdict and the argument behind it.
 *
 * The first sentence is the call; the rest is the evidence. Presenting them at
 * two different weights is what makes a paragraph read as analysis rather than
 * as a caption, and it needs no structured data the pipeline does not already
 * produce: it is one string, split on the first full stop.
 */
export function splitRead(text: string | null): { lead: string; body: string } {
  if (!text) return { lead: "", body: "" };
  const trimmed = text.trim();
  const end = trimmed.search(/\.\s/);
  if (end === -1) return { lead: trimmed, body: "" };
  return {
    lead: trimmed.slice(0, end + 1).trim(),
    body: trimmed.slice(end + 1).trim(),
  };
}

/**
 * Turn a stored selection into the words a bettor reads on the slip.
 *
 * The pipeline stores selections positionally — "home", "away", "draw",
 * "over", "under", "yes", "no" — because that is what the model prices and
 * what settles cleanly regardless of which club is which. On the card the
 * pick is the headline, so a positional token becomes the actual team name
 * (from the fixture) or the plain-language market outcome. Anything already
 * written out (older rows, demo snapshots) passes through untouched.
 */
export function selectionLabel(
  selection: string | null,
  home: string | null | undefined,
  away: string | null | undefined,
): string {
  if (!selection) return "";
  switch (selection.trim().toLowerCase()) {
    case "home":
      return home || "Home";
    case "away":
      return away || "Away";
    case "draw":
      return "Draw";
    case "over":
      return "Over 2.5 goals";
    case "under":
      return "Under 2.5 goals";
    case "yes":
      return "Both teams to score";
    case "no":
      return "Not both teams to score";
    default:
      return selection;
  }
}

/**
 * The market a pick sits in, named the way a slip names it rather than by its
 * internal key. Unknown or already-friendly values pass through.
 */
export function marketLabel(market: string | null): string {
  if (!market) return "";
  const m = market.trim().toLowerCase();
  if (m === "1x2") return "Match result";
  if (m === "btts") return "Both teams to score";
  if (m.startsWith("ou_")) return "Total goals";
  return market;
}
