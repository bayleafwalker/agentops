export function CockpitNav() {
  const items = [
    { href: "#overview", label: "overview" },
    { href: "#sprints", label: "sprints" },
    { href: "#work-items", label: "items" },
    { href: "#claims", label: "claims" },
    { href: "#takeup", label: "takeup" },
    { href: "#dispatch", label: "dispatch" },
    { href: "#outcomes", label: "outcomes" },
    { href: "#events", label: "events" },
    { href: "#tweaks", label: "tweaks" }
  ];

  return (
    <nav className="cockpit-nav" aria-label="cockpit sections">
      {items.map((item) => (
        <a key={item.href} href={item.href} className="nav-link">
          {item.label}
        </a>
      ))}
    </nav>
  );
}
