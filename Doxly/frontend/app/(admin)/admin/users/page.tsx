import type { Metadata } from "next";
import { Suspense } from "react";
import { AdminUsersView } from "./users-view";

export const metadata: Metadata = { title: "Admin — Users" };

export default function AdminUsersPage() {
  return (
    <Suspense fallback={null}>
      <AdminUsersView />
    </Suspense>
  );
}
