"use client";

import { useEffect, useState } from "react";
import type { CSSProperties, ReactNode } from "react";
import { CaretDown, CaretUp, Lightning } from "@phosphor-icons/react";
import {
  clubIdentity,
  competitionIdentity,
  competitionSurface,
  readableFill,
} from "@/lib/identity";
import { competitionMedia, competitionPhoto, teamMedia } from "@/lib/media";
import { CountUp } from "./motion";

/* ---------------------------------------------------------------------------
   Club badge

   The real crest where we have one, and a monogram in the club's colours where
   we do not. The fallback is not a placeholder: it is what a club whose crest
   we could not confirm by name is *supposed* to look like, because guessing is
   how Real Sociedad ends up wearing Real Madrid's badge.

   The image is swapped in on the client after it loads, so a crest that 404s
   or a network that never answers leaves the monogram standing rather than a
   broken-image box.
--------------------------------------------------------------------------- */

export function ClubBadge({
  name,
  size = 40,
}: {
  name: string | null | undefined;
  size?: number;
}) {
  const club = clubIdentity(name);
  const { bg, ink } = readableFill(club.primary);
  const media = teamMedia(name);
  const [crestOk, setCrestOk] = useState(Boolean(media?.badge));

  return (
    <span
      aria-hidden
      title={name ?? undefined}
      style={{
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
        width: size,
        height: size,
        flex: "none",
        position: "relative",
        overflow: "hidden",
        borderRadius: size * 0.28,
        background: crestOk ? "transparent" : bg,
        color: ink,
        fontFamily: "var(--cond)",
        fontWeight: 700,
        fontSize: size * 0.34,
        letterSpacing: "0.02em",
        boxShadow: crestOk
          ? "none"
          : "inset 0 1px 0 rgb(255 255 255 / 0.25), 0 2px 8px -2px rgb(0 0 0 / 0.7)",
      }}
    >
      {crestOk && media?.badge ? (
        <img
          src={media.badge}
          alt=""
          width={size}
          height={size}
          loading="lazy"
          decoding="async"
          onError={() => setCrestOk(false)}
          style={{
            width: "100%",
            height: "100%",
            objectFit: "contain",
            filter: "drop-shadow(0 2px 6px rgb(0 0 0 / 0.55))",
          }}
        />
      ) : (
        <>
          <span
            style={{
              position: "absolute",
              inset: 0,
              background: `linear-gradient(210deg, transparent 62%, ${club.secondary} 62%)`,
              opacity: 0.95,
            }}
          />
          <span style={{ position: "relative" }}>{club.abbr}</span>
        </>
      )}
    </span>
  );
}

/** The same crest at poster scale, sitting behind a card as texture. */
export function CrestWatermark({
  name,
  size = 180,
  style,
}: {
  name: string | null | undefined;
  size?: number;
  style?: CSSProperties;
}) {
  const media = teamMedia(name);
  if (!media?.badge) return null;
  return (
    <img
      className="watermark"
      src={media.badge}
      alt=""
      aria-hidden
      loading="lazy"
      decoding="async"
      style={{ width: size, height: size, objectFit: "contain", ...style }}
    />
  );
}

export function CompetitionMark({
  competition,
  size = 34,
}: {
  competition: string | null | undefined;
  size?: number;
}) {
  const c = competitionIdentity(competition);
  const { bg, ink } = readableFill(c.accent);
  const media = competitionMedia(c.key);
  const [emblemOk, setEmblemOk] = useState(Boolean(media?.badge));

  if (emblemOk && media?.badge) {
    return (
      <img
        src={media.badge}
        alt=""
        aria-hidden
        title={c.name}
        width={size}
        height={size}
        loading="lazy"
        decoding="async"
        onError={() => setEmblemOk(false)}
        style={{
          width: size,
          height: size,
          flex: "none",
          objectFit: "contain",
          filter: "drop-shadow(0 2px 6px rgb(0 0 0 / 0.6))",
        }}
      />
    );
  }

  return (
    <span
      aria-hidden
      style={{
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
        width: size,
        height: size,
        flex: "none",
        position: "relative",
        overflow: "hidden",
        borderRadius: size * 0.26,
        background: bg,
        color: ink,
        fontFamily: "var(--cond)",
        fontWeight: 700,
        fontSize: size * 0.3,
        letterSpacing: "0.02em",
        boxShadow: "inset 0 1px 0 rgb(255 255 255 / 0.28)",
      }}
    >
      <span
        style={{
          position: "absolute",
          inset: 0,
          background: `linear-gradient(210deg, transparent 64%, ${c.accent2} 64%)`,
        }}
      />
      <span style={{ position: "relative" }}>{c.short}</span>
    </span>
  );
}

/**
 * A competition section opener.
 *
 * Real competition photography where we resolved some, the generated floodlit
 * treatment where we did not, and the emblem either way. It is a broadcast
 * slab rather than a bordered box: the one shape on the site that is not a
 * rounded rectangle, so a section break reads as a graphic rather than as
 * another card.
 */
export function CompetitionHeader({
  competition,
  right,
}: {
  competition: string | null | undefined;
  right?: ReactNode;
}) {
  const c = competitionIdentity(competition);
  const photo = competitionPhoto(c.key);
  return (
    <div
      className={photo ? "photo photo-flat" : undefined}
      style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        gap: "var(--s-3)",
        minHeight: 76,
        padding: "var(--s-3) var(--s-4)",
        borderRadius: "var(--r-2)",
        overflow: "hidden",
        ...(photo ? {} : competitionSurface(c, 0.6)),
      }}
    >
      {photo && <img src={photo} alt="" aria-hidden loading="lazy" decoding="async" />}
      {/* The competition's colour as a hard edge down the leading side, so the
          section is placeable at a glance even when the photograph is not. */}
      <span
        aria-hidden
        style={{
          position: "absolute",
          left: 0,
          top: 0,
          bottom: 0,
          width: 5,
          background: c.accent,
          boxShadow: `0 0 22px -2px ${c.accent}`,
        }}
      />
      <div className="cluster" style={{ gap: "var(--s-3)", flexWrap: "nowrap", minWidth: 0, position: "relative" }}>
        <CompetitionMark competition={competition} size={34} />
        <div style={{ minWidth: 0 }}>
          <div
            className="cond"
            style={{
              fontWeight: 700,
              fontSize: "1.1875rem",
              letterSpacing: "0.04em",
              textTransform: "uppercase",
              whiteSpace: "nowrap",
              overflow: "hidden",
              textOverflow: "ellipsis",
            }}
          >
            {c.name}
          </div>
          {c.country && (
            <div style={{ color: "var(--ink-3)", fontSize: "var(--t-micro)" }}>{c.country}</div>
          )}
        </div>
      </div>
      <div style={{ position: "relative" }}>{right}</div>
    </div>
  );
}

/* ---------------------------------------------------------------------------
   Time

   The clock is the tension of the whole product. A pick is worth reading
   because it expires.
--------------------------------------------------------------------------- */

function parts(ms: number) {
  const s = Math.max(0, Math.floor(ms / 1000));
  return {
    d: Math.floor(s / 86400),
    h: Math.floor((s % 86400) / 3600),
    m: Math.floor((s % 3600) / 60),
    s: s % 60,
  };
}

/**
 * Ticks to kickoff.
 *
 * It renders nothing on the server and nothing on the first client paint,
 * because a countdown baked into a static export is a countdown that is wrong
 * the moment it is served. The `suppressHydrationWarning` alternative would
 * ship a number that is stale by however long the page sat on the CDN.
 */
export function Countdown({
  to,
  compact = false,
}: {
  to: string;
  compact?: boolean;
}) {
  const [now, setNow] = useState<number | null>(null);

  useEffect(() => {
    setNow(Date.now());
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, []);

  if (now === null) return <span className="num" style={{ opacity: 0 }}>00:00:00</span>;

  const left = new Date(to).getTime() - now;
  if (left <= 0) {
    return (
      <span className="live">
        <span className="live-dot" />
        Kicked off
      </span>
    );
  }

  const { d, h, m, s } = parts(left);
  const urgent = left < 60 * 60 * 1000;
  const text = d > 0 ? `${d}d ${h}h ${m}m` : `${h}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;

  return (
    <span
      className="cond num"
      style={{
        fontWeight: 700,
        fontSize: compact ? "var(--t-small)" : "1.125rem",
        letterSpacing: "0.04em",
        color: urgent ? "var(--brand)" : "var(--ink)",
        fontVariantNumeric: "tabular-nums",
      }}
    >
      {text}
    </span>
  );
}

export function KickoffLine({ at }: { at: string }) {
  const d = new Date(at);
  return (
    <span className="cond" style={{ color: "var(--ink-3)", letterSpacing: "0.05em", textTransform: "uppercase", fontSize: "var(--t-small)" }}>
      {d.toLocaleDateString("en-GB", { weekday: "short", day: "numeric", month: "short", timeZone: "UTC" })}
      {" · "}
      <span className="num">{d.toISOString().slice(11, 16)}</span> UTC
    </span>
  );
}

/* ---------------------------------------------------------------------------
   Price
--------------------------------------------------------------------------- */

export function PriceButton({
  odds,
  book,
  selected = false,
  disabled = false,
  onClick,
  label,
}: {
  odds: number | null;
  book?: string | null;
  selected?: boolean;
  disabled?: boolean;
  onClick?: () => void;
  label?: string;
}) {
  return (
    <button
      type="button"
      className="price"
      data-selected={selected}
      disabled={disabled || odds === null}
      onClick={onClick}
      aria-pressed={selected}
      aria-label={label}
    >
      <span className="price-val">
        {odds === null ? "n/a" : <CountUp to={odds} duration={700} />}
      </span>
      {book && <span className="price-book">{book}</span>}
    </button>
  );
}

/**
 * How the price has moved since we published.
 *
 * A shortening price means the market came to us, which is the single number
 * that tells a reader whether the call was any good before the result lands.
 */
export function Drift({ from, to }: { from: number | null; to: number | null }) {
  if (from === null || to === null || from === to) return null;
  // A shortening price means the market moved toward our call, which is the
  // one number that says something about the pick before the result lands.
  const shortened = to < from;
  return (
    <span className={`drift ${shortened ? "drift-up" : "drift-down"}`}>
      {shortened ? <CaretDown size={11} weight="bold" aria-hidden /> : <CaretUp size={11} weight="bold" aria-hidden />}
      {shortened ? "shortened" : "drifted"} from {from.toFixed(2)}
    </span>
  );
}

export function BestBet() {
  return (
    <span className="chip chip-brand">
      <Lightning size={11} weight="fill" aria-hidden />
      Best bet
    </span>
  );
}
