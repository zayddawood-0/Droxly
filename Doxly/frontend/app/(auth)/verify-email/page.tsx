import type { Metadata } from "next";
import { AuthCard } from "@/components/domain/auth/auth-card";
import { VerifyEmailStatus } from "@/components/domain/auth/verify-email-status";

export const metadata: Metadata = { title: "Verify your email" };

export default async function VerifyEmailPage({
  searchParams,
}: {
  searchParams: Promise<{ token?: string }>;
}) {
  const { token } = await searchParams;

  return (
    <AuthCard
      title="Verify your email"
      description="Confirming your email address."
    >
      <VerifyEmailStatus token={token} />
    </AuthCard>
  );
}
