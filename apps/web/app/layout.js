import "./globals.css";

export const metadata = {
  title: "Agent Cockpit",
  description: "Read-only operator cockpit for agentops workstream E."
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
