import type { Metadata } from "next";
import { AuthCard } from "@/components/domain/auth/auth-card";
import { LoginForm } from "@/components/domain/auth/login-form";

export const metadata: Metadata = { title: "Log in" };

export default function LoginPage() {
  return (
    <AuthCard
      title="Log in"
      description="Welcome back — pick up where you left off."
    >
      <LoginForm />
    </AuthCard>
  );
}
