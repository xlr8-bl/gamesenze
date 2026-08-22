import PageHead from "@/components/PageHead";

export default function NotFound() {
  return (
    <>
      <PageHead
        eyebrow="404"
        title="Off target"
        lede="That page is not on the board. It may have kicked off already, or never existed."
        photoFrom="premier_league"
      />
      <div className="shell" style={{ paddingTop: "var(--s-6)" }}>
        <div className="cluster" style={{ gap: "var(--s-3)" }}>
          <a href="/" className="btn">Back to the front</a>
          <a href="/board/" className="btn btn-ghost">See the board</a>
        </div>
      </div>
    </>
  );
}
