import { describe, it, expect } from "vitest";
import { parseYandexToken } from "../src/auth/yandex";

describe("parseYandexToken", () => {
  it("extracts access_token from a redirect hash", () => {
    const hash = "#access_token=AQAA123&token_type=bearer&expires_in=31536000";
    expect(parseYandexToken(hash)).toBe("AQAA123");
  });
  it("url-decodes the token", () => {
    expect(parseYandexToken("#access_token=ab%2Bcd&x=1")).toBe("ab+cd");
  });
  it("returns null when no token present", () => {
    expect(parseYandexToken("#error=access_denied")).toBeNull();
  });
});
