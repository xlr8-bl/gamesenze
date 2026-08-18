export default function Home() {
  return (
    <main>
      <div className="card">
        <h3>What this is</h3>
        <p className="meta">
          Four football picks and two NBA picks a day, at most. Every pick is
          read by a person before it publishes, and any pick whose data we
          cannot verify does not publish at all.
        </p>
      </div>

      <div className="card">
        <h3>What we show you that others don&apos;t</h3>
        <p className="meta">
          Where a factor had too thin a sample to use, we say so on the pick
          rather than quietly leaving it out. Where our request budget forces
          less frequent price updates, the board says that too. A day with no
          picks is a normal day.
        </p>
      </div>

      <div className="card">
        <h3>The combo builder</h3>
        <p className="meta">
          Stack two to five published picks and see the maths — combined price,
          what a stake returns, and how combos of that size have actually landed
          in our record. It does not place anything. You copy the details to
          your own book.
        </p>
      </div>
    </main>
  );
}
