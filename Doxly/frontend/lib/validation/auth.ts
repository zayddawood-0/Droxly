import { z } from "zod";

/**
 * Mirrors the backend Pydantic validation rules field-for-field
 * (skills/frontend.md §7) so a client-side error and a server-side error
 * never disagree about what's valid. Password policy source: FR-AUTH-001 /
 * specs/security.md §2.1 — min 8 chars, at least one letter, at least one
 * digit. Client-side validation is a UX convenience only, never the security
 * boundary (skills/backend.md §9) — the backend re-validates unconditionally.
 */
const isValidEmail = (value: string) => z.email().safeParse(value).success;

export const emailSchema = z
  .string()
  .trim()
  .min(1, "Enter your email address")
  .refine(isValidEmail, "Enter a valid email address");

export const passwordPolicySchema = z
  .string()
  .min(8, "Use at least 8 characters")
  .regex(/[A-Za-z]/, "Include at least one letter")
  .regex(/[0-9]/, "Include at least one number");

export const loginSchema = z.object({
  email: emailSchema,
  password: z.string().min(1, "Enter your password"),
});
export type LoginValues = z.infer<typeof loginSchema>;

export const registerSchema = z.object({
  display_name: z.string().trim().min(1, "Enter your name"),
  email: emailSchema,
  password: passwordPolicySchema,
});
export type RegisterValues = z.infer<typeof registerSchema>;

export const forgotPasswordSchema = z.object({
  email: emailSchema,
});
export type ForgotPasswordValues = z.infer<typeof forgotPasswordSchema>;

export const resetPasswordSchema = z
  .object({
    password: passwordPolicySchema,
    confirmPassword: z.string().min(1, "Re-enter your new password"),
  })
  .refine((data) => data.password === data.confirmPassword, {
    message: "Passwords don't match",
    path: ["confirmPassword"],
  });
export type ResetPasswordValues = z.infer<typeof resetPasswordSchema>;

/** Evaluates the same three policy checks used by passwordPolicySchema, for the strength meter. */
export function evaluatePasswordPolicy(password: string) {
  return {
    hasMinLength: password.length >= 8,
    hasLetter: /[A-Za-z]/.test(password),
    hasDigit: /[0-9]/.test(password),
  };
}
