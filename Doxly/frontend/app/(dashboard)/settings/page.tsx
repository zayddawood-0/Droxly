import type { Metadata } from "next";
import { PageHeader } from "@/components/layout/page-header";
import { PhasePlaceholder } from "@/components/layout/phase-placeholder";

export const metadata: Metadata = { title: "Settings" };

export default function SettingsPage() {
  return (
    <>
      <PageHeader
        title="Settings"
        description="Profile, security, plan, and data controls."
      />
      <PhasePlaceholder
        phase="Phase 2 / Phase 4 — Auth & Document Management"
        requirements="FR-USER-001, FR-USER-002, FR-AUTH-008, FR-EXPORT-004"
      />
    </>
  );
}
