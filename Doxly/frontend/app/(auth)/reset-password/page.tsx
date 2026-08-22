import type { Metadata } from "next";
import { AuthCard } from "@/components/domain/auth/auth-card";
import { ResetPasswordForm } from "@/components/domain/auth/reset-password-form";

export const metadata: Metadata = { title: "Set a new password" };

export default async function ResetPasswordPage({
  searchParams,
}: {
  searchParams: Promise<{ token?: string }>;
}) {
  const { token } = await searchParams;

  return (
    <AuthCard
      title="Set a new password"
      description="Choose a new password for your account."
    >
      <ResetPasswordForm token={token} />
    </AuthCard>
  );
}
