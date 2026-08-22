import { Notice } from "@/components/ui";
import PageHead from "@/components/PageHead";

const HELP = [
  ["GamCare", "Free, confidential support and a 24-hour helpline.", "0808 8020 133", "https://www.gamcare.org.uk"],
  ["BeGambleAware", "Advice, self-assessment and a directory of local support.", "", "https://www.begambleaware.org"],
  ["GAMSTOP", "Self-exclude from every online operator licensed in Great Britain, in one place.", "", "https://www.gamstop.co.uk"],
  ["Gamblers Anonymous", "Peer support meetings, in person and online.", "", "https://www.gamblersanonymous.org.uk"],
];

export default function ResponsibleGambling() {
  return (
    <>
      <PageHead
        eyebrow="Responsible gambling"
        title="This can cost you more than money"
        lede="We publish analysis about betting, so we have an obligation to be straight about what betting does to people. This page is not a formality."
      />

      <div className="shell shell-tight prose" style={{ paddingTop: "var(--s-6)" }}>
        <Notice tone="caution">
          If gambling has stopped being a choice, stop reading this site and
          call GamCare on 0808 8020 133. It is free, confidential, and open
          around the clock.
        </Notice>

        <h2 style={{ marginTop: "var(--s-6)" }}>What we are and are not</h2>
        <p>
          GameSenze publishes analysis. We do not hold funds, accept stakes,
          settle bets or take a cut of anything you win or lose. We are not a
          bookmaker and we are not licensed as one, because we never handle a
          wager.
        </p>
        <p>
          We also earn nothing from where you bet. There are no affiliate links
          on this site, so no bookmaker pays us for sending you to them, and
          nothing we publish is shaped by which book you use.
        </p>

        <h2>What a positive record does not mean</h2>
        <p>
          Our track record is published in full, including the losses, because
          a record you can only see the good half of is worthless. But a
          positive record over the sample we have published is{" "}
          <strong>not</strong> a forecast of the next one. Variance in football
          betting is large enough that a genuinely good method loses over
          stretches long enough to hurt, and a bad one wins over stretches long
          enough to feel like skill.
        </p>
        <p>
          Nothing here is advice, a tip, or a promise. Every pick is one
          reading of one market, with the working shown so you can disagree
          with it.
        </p>

        <h2>Signs worth taking seriously</h2>
        <ul>
          <li>Betting with money set aside for something else.</li>
          <li>Increasing stakes to recover a loss.</li>
          <li>Betting to change how you feel rather than because you fancy a call.</li>
          <li>Hiding the amount, the frequency or the losses from people close to you.</li>
          <li>Feeling you cannot stop for a week without effort.</li>
        </ul>
        <p>
          Any one of those is a reason to talk to someone on the list below.
          Not a reason to read a better tipster.
        </p>

        <h2>Practical limits</h2>
        <ul>
          <li>Set a deposit limit at your bookmaker before you need one. Every UK-licensed operator has to offer them.</li>
          <li>Decide the stake before you read the pick, not after.</li>
          <li>Take a cooling-off period if a week has gone badly. Operators must offer these too.</li>
          <li>If you want out entirely, GAMSTOP blocks every GB-licensed online operator at once.</li>
        </ul>

        <h2>Where to get help</h2>
        <div className="stack-s" style={{ margin: "var(--s-4) 0" }}>
          {HELP.map(([name, line, phone, href]) => (
            <div key={name} className="panel panel-pad">
              <div className="row" style={{ alignItems: "baseline" }}>
                <h3 className="cond" style={{ textTransform: "uppercase", letterSpacing: "0.04em", fontSize: "1.125rem" }}>
                  {name}
                </h3>
                {phone && (
                  <span className="cond num" style={{ color: "var(--brand)", fontWeight: 700, fontSize: "1.125rem" }}>
                    {phone}
                  </span>
                )}
              </div>
              <p style={{ margin: "var(--s-2) 0 var(--s-2)", fontSize: "var(--t-small)" }}>{line}</p>
              <a
                href={href}
                rel="noopener noreferrer"
                target="_blank"
                style={{
                  display: "inline-flex",
                  alignItems: "center",
                  minHeight: 28,
                  color: "var(--brand)",
                  fontSize: "var(--t-small)",
                }}
              >
                {href.replace("https://www.", "")}
              </a>
            </div>
          ))}
        </div>

        <h2>Age</h2>
        <p>
          You must be 18 or over to gamble in the United Kingdom, and 18 or
          over to hold an account here. If you are under 18, this site is not
          for you.
        </p>
      </div>
    </>
  );
}
