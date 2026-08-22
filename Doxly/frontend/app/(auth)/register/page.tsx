import type { Metadata } from "next";
import { AuthCard } from "@/components/domain/auth/auth-card";
import { RegisterForm } from "@/components/domain/auth/register-form";

export const metadata: Metadata = { title: "Create your account" };

export default function RegisterPage() {
  return (
    <AuthCard
      title="Create your account"
      description="Your docs, but smarter — start in under a minute."
    >
      <RegisterForm />
    </AuthCard>
  );
}
