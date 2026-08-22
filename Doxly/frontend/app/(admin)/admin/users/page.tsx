import type { Metadata } from "next";
import { PageHeader } from "@/components/layout/page-header";
import { PhasePlaceholder } from "@/components/layout/phase-placeholder";

export const metadata: Metadata = { title: "Admin — Users" };

export default function AdminUsersPage() {
  return (
    <>
      <PageHeader
        title="Users"
        description="Account/operational metadata only — never document, chat, or extraction content."
      />
      <PhasePlaceholder
        phase="Phase 2 / 4, hardened in 15"
        requirements="FR-ADMIN-001, NFR-PRIV-004"
      />
    </>
  );
}
