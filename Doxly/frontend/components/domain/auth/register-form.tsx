"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useForm, useWatch } from "react-hook-form";
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
import { PasswordStrengthMeter } from "@/components/domain/auth/password-strength-meter";
import { register as registerAccount } from "@/lib/api/auth";
import { registerSchema, type RegisterValues } from "@/lib/validation/auth";
import { isDoxlyApiError } from "@/lib/types/errors";
import {
  isConnectivityError,
  CONNECTIVITY_ERROR_MESSAGE,
  RATE_LIMITED_MESSAGE,
} from "@/lib/api/error-messages";

/** Register — specs/ui-ux.md §3. Fulfills FR-AUTH-001 (email/password), FR-AUTH-003 (Google). */
export function RegisterForm() {
  const router = useRouter();
  const [bannerError, setBannerError] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);

  const form = useForm<RegisterValues>({
    resolver: zodResolver(registerSchema),
    defaultValues: { display_name: "", email: "", password: "" },
  });
  const password = useWatch({ control: form.control, name: "password" });

  async function onSubmit(values: RegisterValues) {
    setBannerError(null);
    setFormError(null);
    try {
      await registerAccount(values);
      // ui-ux.md §3 specifies a persistent "verify your email" banner on the
      // Dashboard — that requires session-aware Dashboard content (does the
      // current user's email_verified flag), which doesn't exist until a
      // later phase wires GET /users/me into the shell. A toast is the
      // honest interim substitute; swap for the persistent banner once
      // Dashboard has real session data to key it off of.
      toast.success("Account created — check your email to verify it.");
      router.push("/dashboard");
      router.refresh();
    } catch (error) {
      if (isConnectivityError(error)) {
        setBannerError(CONNECTIVITY_ERROR_MESSAGE);
        return;
      }
      if (isDoxlyApiError(error) && error.isRateLimited) {
        setFormError(RATE_LIMITED_MESSAGE);
        return;
      }
      if (isDoxlyApiError(error) && error.isValidationError && error.fields) {
        for (const [field, message] of Object.entries(error.fields)) {
          if (field in values) {
            form.setError(field as keyof RegisterValues, { message });
          }
        }
        return;
      }
      // Duplicate email and every other registration failure share one
      // generic message (NFR-SEC-006) — never "email already registered."
      setFormError("We couldn't create your account. Check your details and try again.");
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
        <Field data-invalid={!!form.formState.errors.display_name}>
          <FieldLabel htmlFor="register-name">Name</FieldLabel>
          <Input
            id="register-name"
            autoComplete="name"
            aria-invalid={!!form.formState.errors.display_name}
            {...form.register("display_name")}
          />
          <FieldError errors={[form.formState.errors.display_name]} />
        </Field>

        <Field data-invalid={!!form.formState.errors.email}>
          <FieldLabel htmlFor="register-email">Email</FieldLabel>
          <Input
            id="register-email"
            type="email"
            autoComplete="email"
            aria-invalid={!!form.formState.errors.email}
            {...form.register("email")}
          />
          <FieldError errors={[form.formState.errors.email]} />
        </Field>

        <Field data-invalid={!!form.formState.errors.password}>
          <FieldLabel htmlFor="register-password">Password</FieldLabel>
          <Input
            id="register-password"
            type="password"
            autoComplete="new-password"
            aria-invalid={!!form.formState.errors.password}
            {...form.register("password")}
          />
          <PasswordStrengthMeter password={password ?? ""} />
        </Field>

        {formError && (
          <p role="alert" className="text-sm text-danger">
            {formError}
          </p>
        )}

        <Field>
          <Button type="submit" disabled={form.formState.isSubmitting}>
            {form.formState.isSubmitting && (
              <Loader2 className="animate-spin" aria-hidden="true" />
            )}
            Create account
          </Button>
        </Field>

        <FieldSeparator>or</FieldSeparator>

        <GoogleButton label="Continue with Google" />
      </FieldGroup>

      <p className="mt-5 text-center text-sm text-muted-foreground">
        Already have an account?{" "}
        <Link href="/login" className="text-foreground hover:underline">
          Log in
        </Link>
      </p>
    </form>
  );
}
