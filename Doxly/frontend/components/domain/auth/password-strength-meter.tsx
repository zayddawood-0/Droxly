import { evaluatePasswordPolicy } from "@/lib/validation/auth";
import { cn } from "@/lib/utils";

/**
 * Segmented, non-decorative meter that reflects the actual password policy
 * (length + letter + number — specs/ui-ux.md §3) rather than a generic
 * entropy score. Carries a text equivalent alongside color, for screen
 * readers and color-blind users (NFR-A11Y-001).
 */
export function PasswordStrengthMeter({ password }: { password: string }) {
  const { hasMinLength, hasLetter, hasDigit } =
    evaluatePasswordPolicy(password);
  const metCount = [hasMinLength, hasLetter, hasDigit].filter(Boolean).length;

  if (password.length === 0) return null;

  const label =
    metCount === 3
      ? "Looks good"
      : metCount === 0
        ? "Too short"
        : "Add what's missing below";
  const tone =
    metCount === 3 ? "success" : metCount === 0 ? "danger" : "warning";

  return (
    <div className="mt-1.5" aria-live="polite">
      <div className="flex gap-1" role="presentation">
        {[0, 1, 2].map((segment) => (
          <span
            key={segment}
            aria-hidden="true"
            className={cn(
              "h-1 flex-1 rounded-full bg-muted transition-colors",
              segment < metCount &&
                (tone === "success"
                  ? "bg-success"
                  : tone === "warning"
                    ? "bg-warning"
                    : "bg-danger"),
            )}
          />
        ))}
      </div>
      <ul className="mt-1.5 flex flex-col gap-0.5 text-xs text-muted-foreground">
        <PolicyRow met={hasMinLength}>At least 8 characters</PolicyRow>
        <PolicyRow met={hasLetter}>At least one letter</PolicyRow>
        <PolicyRow met={hasDigit}>At least one number</PolicyRow>
      </ul>
      <span className="sr-only">Password strength: {label}</span>
    </div>
  );
}

function PolicyRow({ met, children }: { met: boolean; children: string }) {
  return (
    <li className={cn("flex items-center gap-1.5", met && "text-success")}>
      <span aria-hidden="true">{met ? "✓" : "·"}</span>
      {children}
    </li>
  );
}
