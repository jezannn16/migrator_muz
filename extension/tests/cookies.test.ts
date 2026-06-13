import { describe, it, expect, vi, beforeEach } from "vitest";
import { getCookie } from "../src/chrome/cookies";

beforeEach(() => {
  (globalThis as any).chrome = {
    cookies: {
      get: vi.fn(async ({ name }: { name: string }) =>
        name === "SAPISID" ? { value: "SECRET" } : null),
    },
  };
});

describe("getCookie", () => {
  it("returns the cookie value when present", async () => {
    expect(await getCookie("https://music.youtube.com", "SAPISID")).toBe("SECRET");
  });
  it("returns null when cookie missing", async () => {
    expect(await getCookie("https://music.youtube.com", "NOPE")).toBeNull();
  });
});
