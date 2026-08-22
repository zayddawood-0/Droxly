"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useForm, useWatch } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { Loader2, LinkIcon } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Field, FieldGroup, FieldLabel, FieldError } from "@/components/ui/field";
import { FormErrorBanner } from "@/components/domain/auth/form-error-banner";
import { PasswordStrengthMeter } from "@/components/domain/auth/password-strength-meter";
import { confirmPasswordReset } from "@/lib/api/auth";
import {
  resetPasswordSchema,
  type ResetPasswordValues,
} from "@/lib/validation/auth";
import { isDoxlyApiError } from "@/lib/types/errors";
import {
  isConnectivityError,
  CONNECTIVITY_ERROR_MESSAGE,
} from "@/lib/api/error-messages";

/** Reset Password — fulfills FR-AUTH-007 step 2. */
export function ResetPasswordForm({ token }: { token: string | undefined }) {
  const router = useRouter();
  const [bannerError, setBannerError] = useState<string | null>(null);
  const [tokenError, setTokenError] = useState<string | null>(null);

  const form = useForm<ResetPasswordValues>({
    resolver: zodResolver(resetPasswordSchema),
    defaultValues: { password: "", confirmPassword: "" },
  });
  const password = useWatch({ control: form.control, name: "password" });

  async function onSubmit(values: ResetPasswordValues) {
    if (!token) return;
    setBannerError(null);
    setTokenError(null);
    try {
      await confirmPasswordReset({ token, new_password: values.password });
      toast.success("Password updated — log in with your new password.");
      router.push("/login");
    } catch (error) {
      if (isConnectivityError(error)) {
        setBannerError(CONNECTIVITY_ERROR_MESSAGE);
        return;
      }
      if (isDoxlyApiError(error) && error.isValidationError && error.fields?.new_password) {
        form.setError("password", { message: error.fields.new_password });
        return;
      }
      setTokenError(
        "This link has expired or is no longer valid. Request a new one to continue.",
      );
    }
  }

  if (!token || tokenError) {
    return (
      <div className="flex flex-col items-center gap-3 text-center">
        <LinkIcon className="size-8 text-muted-foreground" aria-hidden="true" />
        <p className="text-sm text-muted-foreground">
          {tokenError ??
            "This password reset link is missing or malformed."}
        </p>
        <Link
          href="/forgot-password"
          className="text-sm text-foreground hover:underline"
        >
          Request a new link
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
        <Field data-invalid={!!form.formState.errors.password}>
          <FieldLabel htmlFor="reset-password">New password</FieldLabel>
          <Input
            id="reset-password"
            type="password"
            autoComplete="new-password"
            aria-invalid={!!form.formState.errors.password}
            {...form.register("password")}
          />
          <PasswordStrengthMeter password={password ?? ""} />
        </Field>

        <Field data-invalid={!!form.formState.errors.confirmPassword}>
          <FieldLabel htmlFor="reset-confirm-password">
            Confirm new password
          </FieldLabel>
          <Input
            id="reset-confirm-password"
            type="password"
            autoComplete="new-password"
            aria-invalid={!!form.formState.errors.confirmPassword}
            {...form.register("confirmPassword")}
          />
          <FieldError errors={[form.formState.errors.confirmPassword]} />
        </Field>

        <Field>
          <Button type="submit" disabled={form.formState.isSubmitting}>
            {form.formState.isSubmitting && (
              <Loader2 className="animate-spin" aria-hidden="true" />
            )}
            Update password
          </Button>
        </Field>
      </FieldGroup>
    </form>
  );
}
