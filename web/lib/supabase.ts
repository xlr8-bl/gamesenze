import { createClient, type SupabaseClient } from "@supabase/supabase-js";

/**
 * REQ-BUDGET-2: the browser never calls a vendor API. Every read on every page
 * comes from Supabase, through the anon key and row-level security. No vendor
 * key is ever shipped to the client, and there is no proxy route that would let
 * one leak — the site is a static export with no server at all.
 */
const url = process.env.NEXT_PUBLIC_SUPABASE_URL ?? "";
const anonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY ?? "";

export const isConfigured = Boolean(url && anonKey);

let client: SupabaseClient | null = null;

/**
 * Created on first use, not at module load.
 *
 * `createClient` throws on an empty URL, and the static export prerenders
 * these pages at build time — so a module-scope client makes the whole build
 * depend on secrets being present. Lazy construction lets the page render its
 * empty state instead, which is also what a reader should see if the
 * connection is misconfigured in production.
 */
export function getSupabase(): SupabaseClient {
  if (!client) {
    client = createClient(url, anonKey, { auth: { persistSession: true } });
  }
  return client;
}

export type Pick = {
  id: string;
  fixture_id: string;
  market: string;
  selection: string;
  confidence_tag: "lean" | "strong_lean" | "best_bet" | null;
  stakes_tags: string[] | null;
  internal_prob: number | null;
  capture_odds: number | null;
  capture_bookmaker: string | null;
  reasoning_full: string | null;
  valid_factors: string[] | null;
  excluded_factors: ExcludedFactor[] | null;
  published_at: string | null;
  result: "won" | "lost" | "push" | "void" | null;
  sport: string;
  kickoff_at: string;
  home_team: string | null;
  away_team: string | null;
  latest_odds: number | null;
  latest_bookmaker: string | null;
  latest_odds_at: string | null;
};

/** REQ-QA-2: a factor we could not use is shown, never silently dropped. */
export type ExcludedFactor = {
  factor: string;
  disposition: "excluded" | "provisional";
  n: number;
  minimum: number;
  message: string;
};

export type BudgetStatus = {
  provider: string;
  pct_used: number;
  ladder_rung: "normal" | "reduced" | "closing_only" | "exhausted";
};

export async function fetchBoard(): Promise<Pick[]> {
  if (!isConfigured) return [];
  const { data, error } = await getSupabase()
    .from("v_published_picks")
    .select("*")
    .order("kickoff_at", { ascending: true });
  if (error) throw error;
  return (data ?? []) as Pick[];
}

export async function fetchBudgetStatus(): Promise<BudgetStatus[]> {
  if (!isConfigured) return [];
  const { data, error } = await getSupabase()
    .from("v_budget_status")
    .select("provider, pct_used, ladder_rung");
  if (error) throw error;
  return (data ?? []) as BudgetStatus[];
}
