"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { Loader2 } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Field,
  FieldGroup,
  FieldLabel,
  FieldError,
  FieldSeparator,
} from "@/components/ui/field";
import { FormErrorBanner } from "@/components/domain/auth/form-error-banner";
import { GoogleButton } from "@/components/domain/auth/google-button";
import { login } from "@/lib/api/auth";
import { loginSchema, type LoginValues } from "@/lib/validation/auth";
import { isDoxlyApiError } from "@/lib/types/errors";
import {
  isConnectivityError,
  CONNECTIVITY_ERROR_MESSAGE,
  RATE_LIMITED_MESSAGE,
} from "@/lib/api/error-messages";

/** Login — specs/ui-ux.md §2. Fulfills FR-AUTH-003 (Google), FR-AUTH-004 (email/password). */
export function LoginForm() {
  const router = useRouter();
  const [bannerError, setBannerError] = useState<string | null>(null);
  const [credentialError, setCredentialError] = useState<string | null>(null);

  const form = useForm<LoginValues>({
    resolver: zodResolver(loginSchema),
    defaultValues: { email: "", password: "" },
  });

  async function onSubmit(values: LoginValues) {
    setBannerError(null);
    setCredentialError(null);
    try {
      const user = await login(values);
      toast.success(`Welcome back, ${user.display_name}.`);
      router.push("/dashboard");
      router.refresh();
    } catch (error) {
      if (isConnectivityError(error)) {
        setBannerError(CONNECTIVITY_ERROR_MESSAGE);
        return;
      }
      if (isDoxlyApiError(error) && error.isRateLimited) {
        setCredentialError(RATE_LIMITED_MESSAGE);
        return;
      }
      if (isDoxlyApiError(error) && error.status === 403) {
        setCredentialError(
          "This account has been suspended. Contact support if this seems wrong.",
        );
        return;
      }
      // 401 invalid_credentials, or anything else 4xx-shaped: a single
      // generic message regardless of cause (NFR-SEC-006 — never reveal
      // whether the email exists).
      setCredentialError("Invalid email or password.");
    }
  }

  return (
    <form onSubmit={form.handleSubmit(onSubmit)} noValidate>
      {bannerError && (
        <FormErrorBanner
          message={bannerError}
          onDismiss={() => setBannerError(null)}
        />
      )}
      <FieldGroup>
        <Field data-invalid={!!form.formState.errors.email}>
          <FieldLabel htmlFor="login-email">Email</FieldLabel>
          <Input
            id="login-email"
            type="email"
            autoComplete="email"
            aria-invalid={!!form.formState.errors.email}
            {...form.register("email")}
          />
          <FieldError errors={[form.formState.errors.email]} />
        </Field>

        <Field data-invalid={!!form.formState.errors.password}>
          <div className="flex items-center justify-between">
            <FieldLabel htmlFor="login-password">Password</FieldLabel>
            <Link
              href="/forgot-password"
              className="text-xs text-muted-foreground hover:text-foreground hover:underline"
            >
              Forgot password?
            </Link>
          </div>
          <Input
            id="login-password"
            type="password"
            autoComplete="current-password"
            aria-invalid={!!form.formState.errors.password}
            {...form.register("password")}
          />
          <FieldError errors={[form.formState.errors.password]} />
        </Field>

        {credentialError && (
          <p role="alert" className="text-sm text-danger">
            {credentialError}
          </p>
        )}

        <Field>
          <Button type="submit" disabled={form.formState.isSubmitting}>
            {form.formState.isSubmitting && (
              <Loader2 className="animate-spin" aria-hidden="true" />
            )}
            Log in
          </Button>
        </Field>

        <FieldSeparator>or</FieldSeparator>

        <GoogleButton label="Continue with Google" />
      </FieldGroup>

      <p className="mt-5 text-center text-sm text-muted-foreground">
        Don&apos;t have an account?{" "}
        <Link href="/register" className="text-foreground hover:underline">
          Sign up
        </Link>
      </p>
    </form>
  );
}
