import type { ReactNode } from "react";

/**
 * The opener every page that is not the board or the home page shares.
 *
 * A lime wash rather than a competition's colours: these pages belong to the
 * product, not to a fixture, and borrowing a competition palette for a terms
 * page would say something untrue about who publishes it.
 */
export default function PageHead({
  eyebrow,
  title,
  lede,
  children,
}: {
  eyebrow?: string;
  title: string;
  lede?: string;
  children?: ReactNode;
}) {
  return (
    <div
      style={{
        borderBottom: "1px solid var(--line)",
        backgroundColor: "#0A0F07",
        backgroundImage: [
          "radial-gradient(90% 130% at 6% -30%, rgb(216 243 43 / 0.42) 0%, transparent 58%)",
          "radial-gradient(70% 90% at 88% -10%, rgb(216 243 43 / 0.14) 0%, transparent 62%)",
          "repeating-linear-gradient(100deg, rgb(255 255 255 / 0.03) 0 22px, transparent 22px 44px)",
          "linear-gradient(180deg, transparent 42%, rgb(4 6 10 / 0.72) 100%)",
        ].join(", "),
        marginTop: -68,
        paddingTop: 68,
      }}
    >
      <div className="shell" style={{ padding: "var(--s-7) var(--s-4) var(--s-6)" }}>
        {eyebrow && (
          <div className="label" style={{ color: "var(--brand)", marginBottom: "var(--s-2)" }}>
            {eyebrow}
          </div>
        )}
        <h1 className="poster" style={{ fontSize: "clamp(2.25rem, 1.6rem + 3vw, 4rem)", maxWidth: "16ch" }}>
          {title}
        </h1>
        {lede && (
          <p style={{ color: "var(--ink-2)", marginTop: "var(--s-4)", fontSize: "1.0625rem", maxWidth: "56ch" }}>
            {lede}
          </p>
        )}
        {children}
      </div>
    </div>
  );
}
