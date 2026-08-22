import PageHead from "@/components/PageHead";
import { Notice } from "@/components/ui";

export default function Terms() {
  return (
    <>
      <PageHead
        eyebrow="Legal"
        title="Terms of service"
        lede="Plain English, because a document nobody can read is a document nobody has agreed to."
      />
      <div className="shell shell-tight prose" style={{ paddingTop: "var(--s-6)" }}>
        <Notice tone="caution">
          This is a working draft written for review, not legal advice, and it
          has not been through a solicitor. Do not rely on it as the operative
          agreement until it has.
        </Notice>

        <h2 style={{ marginTop: "var(--s-6)" }}>1. What this service is</h2>
        <p>
          GameSenze publishes statistical analysis of football fixtures,
          including our own estimate of an outcome&apos;s probability and the
          bookmaker prices we observed. That is the entire service.
        </p>
        <p>
          We do not accept, hold, place, broker or settle bets. We are not a
          bookmaker, a betting intermediary or a financial services firm, and
          we hold no gambling licence because we never handle a stake. Any bet
          you place is between you and your own bookmaker.
        </p>

        <h2>2. Eligibility</h2>
        <p>
          You must be 18 or over to hold an account. You must not use the
          service where doing so breaks the law where you are, and it is your
          responsibility to know whether it does.
        </p>

        <h2>3. No guarantee, no advice</h2>
        <p>
          Nothing published here is advice, a recommendation to stake money, or
          a prediction we stand behind as fact. Our probabilities are
          estimates from models that are wrong some of the time, in ways we
          publish rather than hide. Past results, including the track record on
          this site, do not predict future results.
        </p>
        <p>
          <strong>
            You are solely responsible for every bet you place and every pound
            you lose.
          </strong>
        </p>

        <h2>4. Prices</h2>
        <p>
          Every price shown carries the time we read it. Prices move; the one
          on your screen may already be stale, and the one at your bookmaker is
          the only one that counts. Confirm before you stake.
        </p>

        <h2>5. Your account</h2>
        <ul>
          <li>Keep your credentials to yourself. Activity under your account is treated as yours.</li>
          <li>One person per account. Do not resell, republish or redistribute what you read here.</li>
          <li>Do not scrape the site or hammer it with automated requests.</li>
          <li>Tell us promptly if you think someone else has got into your account.</li>
        </ul>

        <h2>6. Subscriptions</h2>
        <p>
          Paid plans renew monthly until cancelled. Cancel any time from your
          account page and access continues to the end of the period already
          paid for. We do not pro-rate part months. If we materially reduce
          what a plan includes mid-period, you may cancel and we will refund
          the unused part.
        </p>

        <h2>7. Availability</h2>
        <p>
          We aim to publish daily and often do not, because a day whose data
          does not clear verification is a day we publish nothing. An empty
          board is the service working as designed, not an outage, and it is
          not grounds for a refund.
        </p>

        <h2>8. Liability</h2>
        <p>
          To the fullest extent the law allows, we are not liable for gambling
          losses, lost profits, or any indirect or consequential loss arising
          from your use of the service. Where liability cannot be excluded, it
          is limited to the amount you paid us in the twelve months before the
          claim. Nothing here limits liability for death or personal injury
          caused by negligence, or for fraud.
        </p>

        <h2>9. Ending it</h2>
        <p>
          You may close your account at any time. We may suspend or close an
          account that breaks these terms, and will say why unless the law
          stops us.
        </p>

        <h2>10. Changes</h2>
        <p>
          We will give at least 30 days&apos; notice by email before any change
          that materially reduces what you get. Continuing to use the service
          after that is acceptance; if you would rather not, cancel and we will
          refund the unused part of the period.
        </p>

        <h2>11. Law</h2>
        <p>
          These terms are governed by the law of England and Wales, and the
          courts of England and Wales have exclusive jurisdiction.
        </p>
      </div>
    </>
  );
}
