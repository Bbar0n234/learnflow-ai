import { AxiosError, AxiosHeaders } from "axios";
import { describe, expect, it } from "vitest";

import { isSecurityViolation } from "./security-error";

// Unit: recognises the security-policy-violation problem+json marker.

function axiosErrorWith(status: number, data: unknown): AxiosError {
  const err = new AxiosError("Request failed");
  err.response = {
    status,
    statusText: "",
    data,
    headers: {},
    config: { headers: new AxiosHeaders() },
  };
  return err;
}

describe("isSecurityViolation", () => {
  it("is true for a 422 with the security-policy-violation type", () => {
    const err = axiosErrorWith(422, {
      type: "urn:learnflow:security-policy-violation",
    });
    expect(isSecurityViolation(err)).toBe(true);
  });

  it("is false for a 422 with a different type", () => {
    const err = axiosErrorWith(422, { type: "urn:learnflow:validation" });
    expect(isSecurityViolation(err)).toBe(false);
  });

  it("is false for the right type but the wrong status", () => {
    const err = axiosErrorWith(400, {
      type: "urn:learnflow:security-policy-violation",
    });
    expect(isSecurityViolation(err)).toBe(false);
  });

  it("is false for a non-Axios error", () => {
    expect(isSecurityViolation(new Error("boom"))).toBe(false);
    expect(isSecurityViolation(null)).toBe(false);
  });
});
