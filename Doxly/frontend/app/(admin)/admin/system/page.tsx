import type { Metadata } from "next";
import { AdminSystemView } from "./system-view";

export const metadata: Metadata = { title: "Admin — System Health" };

export default function AdminSystemPage() {
  return <AdminSystemView />;
}
