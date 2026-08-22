

const COLUMNS: { title: string; links: [string, string][] }[] = [
  {
    title: "The product",
    links: [
      ["Board", "/board/"],
      ["Record", "/record/"],
      ["Combo builder", "/combo-builder/"],
      ["Pricing", "/pricing/"],
    ],
  },
  {
    title: "Account",
    links: [
      ["Sign in", "/signin/"],
      ["Create an account", "/signup/"],
    ],
  },
  {
    title: "Legal",
    links: [
      ["Terms of service", "/terms/"],
      ["Privacy policy", "/privacy/"],
      ["Responsible gambling", "/responsible-gambling/"],
    ],
  },
];

export default function Footer() {
  return (
    <footer style={{ marginTop: "var(--s-8)", borderTop: "1px solid var(--line)" }}>
      {/*
        The one place the site states plainly what it is not. It gets the same
        treatment as a competition banner rather than being set in grey at the
        bottom, because a reader who misses it is a reader who thinks they
        placed a bet here.
      */}
      <div
        style={{
          borderBottom: "1px solid var(--line)",
          backgroundColor: "#0B1008",
          backgroundImage: [
            "radial-gradient(110% 100% at 8% -25%, rgb(216 243 43 / 0.40) 0%, transparent 58%)",
            "radial-gradient(80% 80% at 96% 0%, rgb(216 243 43 / 0.10) 0%, transparent 62%)",
            "repeating-linear-gradient(100deg, rgb(255 255 255 / 0.03) 0 22px, transparent 22px 44px)",
            "linear-gradient(180deg, transparent 40%, rgb(4 6 10 / 0.7) 100%)",
          ].join(", "),
        }}
      >
        <div className="shell" style={{ padding: "var(--s-6) var(--s-4)" }}>
          <p
            className="poster"
            style={{ fontSize: "clamp(1.5rem, 1rem + 2.4vw, 2.5rem)", maxWidth: "20ch", marginBottom: "var(--s-3)" }}
          >
            We never take your bet
          </p>
          <p style={{ color: "var(--ink-2)", maxWidth: "58ch" }}>
            GameSenze is analysis. We hold no funds, run no book and settle
            nothing. Every price here is a reading of someone else&apos;s market,
            with the time we read it. You place your own bets, at your own book,
            with your own money.
          </p>
        </div>
      </div>

      <div className="shell" style={{ padding: "var(--s-6) var(--s-4) var(--s-5)" }}>
        <div
          style={{
            display: "grid",
            gap: "var(--s-5)",
            gridTemplateColumns: "repeat(auto-fit, minmax(170px, 1fr))",
          }}
        >
          {COLUMNS.map((col) => (
            <div key={col.title}>
              <div className="label" style={{ marginBottom: "var(--s-2)" }}>{col.title}</div>
              <ul style={{ listStyle: "none", margin: 0, padding: 0, display: "grid", gap: 2 }}>
                {col.links.map(([label, href]) => (
                  <li key={href}>
                    <a
                      href={href}
                      style={{
                        display: "inline-flex",
                        alignItems: "center",
                        minHeight: 28,
                        color: "var(--ink-2)",
                        textDecoration: "none",
                        fontSize: "var(--t-small)",
                      }}
                    >
                      {label}
                    </a>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>

        <p
          className="p-full"
          style={{
            marginTop: "var(--s-6)",
            paddingTop: "var(--s-4)",
            borderTop: "1px solid var(--line)",
            color: "var(--ink-3)",
            fontSize: "var(--t-micro)",
            lineHeight: 1.7,
          }}
        >
          18+. Gambling can be addictive. Free, confidential help is at
          BeGambleAware.org or on 0808 8020 133 in the UK. Odds shown carry the
          time they were captured and are not live quotes; confirm every price
          at your own book before staking. Nothing here is financial advice.
        </p>
      </div>
    </footer>
  );
}
