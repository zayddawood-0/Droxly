"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Loader2, CircleCheck, CircleAlert } from "lucide-react";

import { Button } from "@/components/ui/button";
import { verifyEmail } from "@/lib/api/auth";
import { isConnectivityError, CONNECTIVITY_ERROR_MESSAGE } from "@/lib/api/error-messages";

type Status = "verifying" | "success" | "error";

/** Verify Email — fulfills FR-AUTH-002. Auto-runs on mount against the token in the URL. */
export function VerifyEmailStatus({ token }: { token: string | undefined }) {
  const [status, setStatus] = useState<Status>(token ? "verifying" : "error");
  const [message, setMessage] = useState<string>(
    "This verification link is missing or malformed.",
  );

  useEffect(() => {
    if (!token) return;
    let cancelled = false;

    verifyEmail(token)
      .then(() => {
        if (!cancelled) setStatus("success");
      })
      .catch((error) => {
        if (cancelled) return;
        setMessage(
          isConnectivityError(error)
            ? CONNECTIVITY_ERROR_MESSAGE
            : "This link has expired or is no longer valid.",
        );
        setStatus("error");
      });

    return () => {
      cancelled = true;
    };
  }, [token]);

  if (status === "verifying") {
    return (
      <div
        className="flex flex-col items-center gap-3 py-2 text-center"
        role="status"
        aria-live="polite"
      >
        <Loader2 className="size-8 animate-spin text-muted-foreground" aria-hidden="true" />
        <p className="text-sm text-muted-foreground">Verifying your email…</p>
      </div>
    );
  }

  if (status === "success") {
    return (
      <div className="flex flex-col items-center gap-3 text-center" role="status">
        <CircleCheck className="size-8 text-success" aria-hidden="true" />
        <p className="text-sm text-muted-foreground">
          Your email is verified. You&apos;re all set.
        </p>
        <Button render={<Link href="/dashboard" />} nativeButton={false}>
          Continue to Dashboard
        </Button>
      </div>
    );
  }

  return (
    <div className="flex flex-col items-center gap-3 text-center" role="alert">
      <CircleAlert className="size-8 text-danger" aria-hidden="true" />
      <p className="text-sm text-muted-foreground">{message}</p>
      <Link href="/login" className="text-sm text-foreground hover:underline">
        Back to log in
      </Link>
    </div>
  );
}
