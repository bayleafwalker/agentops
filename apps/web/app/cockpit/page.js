import { CockpitShell } from "../../components/cockpit/cockpit-shell";

export const dynamic = "force-dynamic";

export default function CockpitPage() {
  return (
    <main className="cockpit-page">
      <CockpitShell />
    </main>
  );
}
