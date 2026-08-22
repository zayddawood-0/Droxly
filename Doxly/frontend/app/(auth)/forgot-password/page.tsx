import type { Metadata } from "next";
import { AuthCard } from "@/components/domain/auth/auth-card";
import { ForgotPasswordForm } from "@/components/domain/auth/forgot-password-form";

export const metadata: Metadata = { title: "Reset your password" };

export default function ForgotPasswordPage() {
  return (
    <AuthCard
      title="Reset your password"
      description="We'll email you a link to get back in."
    >
      <ForgotPasswordForm />
    </AuthCard>
  );
}
