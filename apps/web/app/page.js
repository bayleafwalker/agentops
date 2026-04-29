import Link from "next/link";

export default function HomePage() {
  return (
    <main className="home-shell">
      <div className="home-panel">
        <p className="eyebrow">agentops / workstream e</p>
        <h1>Agent Cockpit</h1>
        <p className="home-copy">
          Read-only cockpit scaffold backed by sprintctl postgres, actionctl
          session reads, and audit shard artifacts.
        </p>
        <Link href="/cockpit" className="home-link">
          Open cockpit
        </Link>
      </div>
    </main>
  );
}
