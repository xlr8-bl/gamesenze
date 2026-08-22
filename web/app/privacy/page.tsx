import PageHead from "@/components/PageHead";
import { Notice } from "@/components/ui";

export default function Privacy() {
  return (
    <>
      <PageHead
        eyebrow="Legal"
        title="Privacy policy"
        lede="What we collect, why, and how to make us delete it."
      />
      <div className="shell shell-tight prose" style={{ paddingTop: "var(--s-6)" }}>
        <Notice tone="caution">
          This is a working draft written for review, not legal advice, and it
          has not been through a solicitor or a data protection adviser.
        </Notice>

        <h2 style={{ marginTop: "var(--s-6)" }}>What we collect</h2>
        <ul>
          <li>
            <strong>Your email address and a password hash.</strong> To let you
            sign in. We never store the password itself.
          </li>
          <li>
            <strong>Your subscription status.</strong> Payments are handled by
            our payment processor. Card numbers never reach our servers and we
            never see them.
          </li>
          <li>
            <strong>Combos you choose to save.</strong> Only the ones you
            explicitly save. A combo you are still building lives in your own
            browser and is never sent to us.
          </li>
          <li>
            <strong>Aggregate usage counts.</strong> Which picks get stacked
            together, without any per-person detail attached.
          </li>
        </ul>

        <h2>What we do not collect</h2>
        <p>
          No third-party analytics, no advertising pixels, no session
          recording, no cross-site tracking and no fingerprinting. There are no
          bookmaker affiliate links on this site, so nothing here reports back
          to a bookmaker about you. We do not sell or share personal data with
          anyone for their own purposes.
        </p>
        <p>
          Fonts are served from our own domain rather than a font host, so
          loading a page makes no third-party request at all.
        </p>

        <h2>Why we are allowed to hold it</h2>
        <p>
          Account and subscription data: because we need it to provide the
          service you asked for. Aggregate usage counts: our legitimate
          interest in knowing which parts of the product are used, which is why
          they carry no identity.
        </p>

        <h2>How long we keep it</h2>
        <p>
          Account data until you delete the account, then up to 30 days in
          backups before it ages out. Payment records for six years, because
          tax law requires it. Aggregate counts indefinitely, since they
          identify nobody.
        </p>

        <h2>Your rights</h2>
        <p>
          Under UK GDPR you can ask for a copy of your data, ask us to correct
          it, ask us to delete it, object to processing, or ask for it in a
          portable format. Email us and we will act within one month. You can
          also complain to the Information Commissioner&apos;s Office.
        </p>

        <h2>Cookies</h2>
        <p>
          One cookie, holding your sign-in session. It is strictly necessary,
          so there is no consent banner: there is nothing to consent to. Your
          in-progress combo uses your browser&apos;s local storage, which never
          leaves your device.
        </p>

        <h2>A breach</h2>
        <p>
          If personal data is exposed in a way likely to put you at risk, we
          will tell the ICO within 72 hours and tell you without undue delay,
          in plain terms, including what we do not yet know.
        </p>
      </div>
    </>
  );
}
