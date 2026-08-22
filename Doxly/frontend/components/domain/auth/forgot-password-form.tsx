"use client";

import { useState } from "react";
import Link from "next/link";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { Loader2, MailCheck } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Field, FieldGroup, FieldLabel, FieldError } from "@/components/ui/field";
import { FormErrorBanner } from "@/components/domain/auth/form-error-banner";
import { requestPasswordReset } from "@/lib/api/auth";
import {
  forgotPasswordSchema,
  type ForgotPasswordValues,
} from "@/lib/validation/auth";
import {
  isConnectivityError,
  CONNECTIVITY_ERROR_MESSAGE,
} from "@/lib/api/error-messages";

/** Forgot Password — specs/api.md §1: 202 unconditionally (NFR-SEC-006), so the UI never distinguishes "email found" from "not found." Fulfills FR-AUTH-007 step 1. */
export function ForgotPasswordForm() {
  const [bannerError, setBannerError] = useState<string | null>(null);
  const [submittedEmail, setSubmittedEmail] = useState<string | null>(null);

  const form = useForm<ForgotPasswordValues>({
    resolver: zodResolver(forgotPasswordSchema),
    defaultValues: { email: "" },
  });

  async function onSubmit(values: ForgotPasswordValues) {
    setBannerError(null);
    try {
      await requestPasswordReset(values.email);
      setSubmittedEmail(values.email);
    } catch (error) {
      // Any non-connectivity failure here would itself be a spec violation
      // (the endpoint always returns 202) — still handled, never a blank
      // failure, since a real backend hiccup is still possible.
      setBannerError(
        isConnectivityError(error)
          ? CONNECTIVITY_ERROR_MESSAGE
          : "Something went wrong. Please try again.",
      );
    }
  }

  if (submittedEmail) {
    return (
      <div className="flex flex-col items-center gap-3 text-center">
        <MailCheck className="size-8 text-success" aria-hidden="true" />
        <p className="text-sm text-muted-foreground">
          If an account exists for <strong className="text-foreground">{submittedEmail}</strong>,
          we&apos;ve sent a link to reset your password.
        </p>
        <Link href="/login" className="text-sm text-foreground hover:underline">
          Back to log in
        </Link>
      </div>
    );
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
          <FieldLabel htmlFor="forgot-email">Email</FieldLabel>
          <Input
            id="forgot-email"
            type="email"
            autoComplete="email"
            aria-invalid={!!form.formState.errors.email}
            {...form.register("email")}
          />
          <FieldError errors={[form.formState.errors.email]} />
        </Field>

        <Field>
          <Button type="submit" disabled={form.formState.isSubmitting}>
            {form.formState.isSubmitting && (
              <Loader2 className="animate-spin" aria-hidden="true" />
            )}
            Send reset link
          </Button>
        </Field>
      </FieldGroup>

      <p className="mt-5 text-center text-sm text-muted-foreground">
        Remembered it?{" "}
        <Link href="/login" className="text-foreground hover:underline">
          Log in
        </Link>
      </p>
    </form>
  );
}
