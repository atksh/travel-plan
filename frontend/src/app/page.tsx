import Link from "next/link";

export default function HomePage() {
  return (
    <main className="page-shell">
      <div className="page-frame stack">
        <section className="hero-panel">
          <div className="section-heading">
            <span className="eyebrow">BosoDrive Optimizer</span>
            <h1>Boso Peninsula date planning that can survive delays, traffic, and weather.</h1>
            <p>
              Generate a route, keep it on your iPhone, and re-plan from the
              foreground when lunch runs long or rain starts.
            </p>
          </div>
          <div className="button-row">
            <Link className="primary-button" href="/trips/new">
              Start a new trip
            </Link>
          </div>
        </section>
      </div>
    </main>
  );
}
