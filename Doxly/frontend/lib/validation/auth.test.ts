import { describe, expect, it } from "vitest";
import {
  loginSchema,
  registerSchema,
  resetPasswordSchema,
  evaluatePasswordPolicy,
} from "./auth";

describe("emailSchema (via loginSchema)", () => {
  it("accepts a valid email", () => {
    const result = loginSchema.safeParse({ email: "maya@example.com", password: "x" });
    expect(result.success).toBe(true);
  });

  it("rejects an empty email with a distinct message from an invalid one", () => {
    const empty = loginSchema.safeParse({ email: "", password: "x" });
    const invalid = loginSchema.safeParse({ email: "not-an-email", password: "x" });
    expect(empty.success).toBe(false);
    expect(invalid.success).toBe(false);
    if (!empty.success && !invalid.success) {
      expect(empty.error.issues[0].message).not.toBe(invalid.error.issues[0].message);
    }
  });
});

describe("passwordPolicySchema (via registerSchema) — FR-AUTH-001", () => {
  const base = { display_name: "Maya", email: "maya@example.com" };

  it("accepts a password meeting all three rules", () => {
    const result = registerSchema.safeParse({ ...base, password: "abcd1234" });
    expect(result.success).toBe(true);
  });

  it("rejects a password under 8 characters", () => {
    const result = registerSchema.safeParse({ ...base, password: "ab1" });
    expect(result.success).toBe(false);
  });

  it("rejects a password with no letter", () => {
    const result = registerSchema.safeParse({ ...base, password: "12345678" });
    expect(result.success).toBe(false);
  });

  it("rejects a password with no digit", () => {
    const result = registerSchema.safeParse({ ...base, password: "abcdefgh" });
    expect(result.success).toBe(false);
  });
});

describe("evaluatePasswordPolicy", () => {
  it("reports each policy criterion independently", () => {
    expect(evaluatePasswordPolicy("short")).toEqual({
      hasMinLength: false,
      hasLetter: true,
      hasDigit: false,
    });
    expect(evaluatePasswordPolicy("abcd1234")).toEqual({
      hasMinLength: true,
      hasLetter: true,
      hasDigit: true,
    });
  });
});

describe("resetPasswordSchema", () => {
  it("rejects mismatched passwords, attributed to confirmPassword", () => {
    const result = resetPasswordSchema.safeParse({
      password: "abcd1234",
      confirmPassword: "abcd9999",
    });
    expect(result.success).toBe(false);
    if (!result.success) {
      expect(result.error.issues[0].path).toEqual(["confirmPassword"]);
    }
  });

  it("accepts matching, policy-compliant passwords", () => {
    const result = resetPasswordSchema.safeParse({
      password: "abcd1234",
      confirmPassword: "abcd1234",
    });
    expect(result.success).toBe(true);
  });
});
