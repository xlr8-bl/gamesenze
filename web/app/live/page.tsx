"use client";

import { useEffect, useState } from "react";
import { fetchLive, isConfigured, type LiveMatch } from "@/lib/supabase";
import { Empty, Loading, Notice } from "@/components/ui";
import { LiveCard } from "@/components/live";
import PageHead from "@/components/PageHead";

/**
 * The live hub.
 *
 * Matches in progress, with the score, the clock, the goals so far and the
 * pick riding on each. It polls while the tab is open, because a scoreboard
 * that does not move is not a scoreboard; the interval is gentle and pauses
 * when the tab is hidden so a backgrounded page is not hammering the view.
 */
export default function Live() {
  const [matches, setMatches] = useState<LiveMatch[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!isConfigured) {
      setMatches([]);
      return;
    }
    let live = true;
    const load = () =>
      fetchLive()
        .then((rows) => live && setMatches(rows))
        .catch((e) => live && setError(String(e?.message ?? e)));
    load();
    const id = setInterval(() => {
      if (document.visibilityState === "visible") load();
    }, 30_000);
    return () => {
      live = false;
      clearInterval(id);
    };
  }, []);

  return (
    <>
      <PageHead
        eyebrow="In play now"
        title="Live"
        lede="Every match in progress, its score and its clock, and how the picks riding on it are shaping up."
        photoFrom="ucl"
      />
      <div className="shell stack" style={{ paddingTop: "var(--s-6)" }}>
        {error ? (
          <Notice tone="bad">The live view could not be loaded: {error}</Notice>
        ) : matches === null ? (
          <Loading label="Finding matches in play" />
        ) : matches.length === 0 ? (
          <Empty title="Nothing kicking off right now">
            When a match we cover is in play, its score, its goals and the pick
            on it show up here in real time. Until then, the{" "}
            <a href="/board/">board</a> has what is coming up.
          </Empty>
        ) : (
          <div
            style={{
              display: "grid",
              gap: "var(--s-4)",
              gridTemplateColumns: "repeat(auto-fill, minmax(440px, 1fr))",
            }}
          >
            {matches.map((m, i) => (
              <LiveCard key={m.fixture_id} m={m} index={i} />
            ))}
          </div>
        )}
      </div>
    </>
  );
}
