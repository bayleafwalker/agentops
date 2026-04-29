export const metadata = {
  title: "Agent Cockpit",
  description: "Read-only operator cockpit for agentops workstream E.",
};

export default function CockpitLayout({ children }) {
  return <div className="cockpit-layout">{children}</div>;
}
