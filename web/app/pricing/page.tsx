import { Check, X } from "@phosphor-icons/react/dist/ssr";
import PageHead from "@/components/PageHead";
import { Notice } from "@/components/ui";

const TIERS = [
  {
    name: "Free",
    price: "£0",
    cadence: "always",
    line: "The whole record, and one pick a day.",
    cta: "Create an account",
    href: "/signup/",
    featured: false,
    has: [
      "One published pick per day",
      "The full track record, including the losses",
      "Closing line value on every settled pick",
      "Every data limit named on the card",
    ],
    hasnt: ["The rest of the board", "The combo builder", "Price movement alerts"],
  },
  {
    name: "Full board",
    price: "£12",
    cadence: "a month",
    line: "Everything we publish, the moment it publishes.",
    cta: "Start on the full board",
    href: "/signup/",
    featured: true,
    has: [
      "Every pick, across all 17 competitions",
      "The combo builder, up to five legs",
      "Price movement since we published",
      "Save and settle your own combos",
      "The full track record and CLV",
    ],
    hasnt: [],
  },
];

export default function Pricing() {
  return (
    <>
      <PageHead
        eyebrow="Pricing"
        title="One price. No tipster upsells."
        lede="There is no VIP tier, no accumulator package and no Telegram group. There are two ways to read the same picks, and the record is free to everybody either way."
      />

      <div className="shell" style={{ paddingTop: "var(--s-7)" }}>
        <div
          style={{
            display: "grid",
            gap: "var(--s-4)",
            gridTemplateColumns: "repeat(auto-fit, minmax(290px, 1fr))",
            alignItems: "start",
          }}
        >
          {TIERS.map((t, i) => (
            <div
              key={t.name}
              className="panel panel-pad rise"
              style={{
                ["--i" as string]: i,
                borderColor: t.featured ? "var(--brand)" : "var(--line)",
                boxShadow: t.featured ? "var(--glow-brand)" : "var(--lift-1)",
              }}
            >
              <div className="row" style={{ marginBottom: "var(--s-3)" }}>
                <h2 className="cond" style={{ textTransform: "uppercase", letterSpacing: "0.05em", fontSize: "1.25rem" }}>
                  {t.name}
                </h2>
                {t.featured && <span className="chip chip-brand">Most read</span>}
              </div>

              <div className="cluster" style={{ gap: "var(--s-2)", alignItems: "baseline" }}>
                <span className="poster" style={{ fontSize: "3.25rem", color: t.featured ? "var(--brand)" : "var(--ink)" }}>
                  {t.price}
                </span>
                <span className="cond" style={{ color: "var(--ink-3)", letterSpacing: "0.06em", textTransform: "uppercase" }}>
                  {t.cadence}
                </span>
              </div>
              <p style={{ color: "var(--ink-2)", marginTop: "var(--s-2)" }}>{t.line}</p>

              <a
                href={t.href}
                className={`btn ${t.featured ? "" : "btn-ghost"}`}
                style={{ width: "100%", marginTop: "var(--s-4)" }}
              >
                {t.cta}
              </a>

              <ul
                style={{
                  listStyle: "none",
                  margin: "var(--s-5) 0 0",
                  padding: 0,
                  display: "grid",
                  gap: "var(--s-2)",
                  fontSize: "var(--t-small)",
                }}
              >
                {t.has.map((f) => (
                  <li key={f} className="cluster" style={{ gap: "var(--s-2)", flexWrap: "nowrap", alignItems: "flex-start" }}>
                    <Check size={15} weight="bold" style={{ color: "var(--brand)", flex: "none", marginTop: 3 }} aria-hidden />
                    <span>{f}</span>
                  </li>
                ))}
                {t.hasnt.map((f) => (
                  <li
                    key={f}
                    className="cluster"
                    style={{ gap: "var(--s-2)", flexWrap: "nowrap", alignItems: "flex-start", color: "var(--ink-3)" }}
                  >
                    <X size={15} weight="bold" style={{ flex: "none", marginTop: 3 }} aria-hidden />
                    <span>{f}</span>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>

        <div className="stack-s" style={{ marginTop: "var(--s-6)" }}>
          <Notice>
            Cancel from the account page at any time and the subscription runs
            to the end of the period you already paid for. We do not ask why.
          </Notice>
          <Notice tone="caution">
            No pick is a guarantee, and a positive record over any sample we
            have published so far is not a promise of a positive record over the
            next one. Stake only what you can afford to lose.
          </Notice>
        </div>
      </div>
    </>
  );
}
