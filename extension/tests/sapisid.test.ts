import { describe, it, expect } from "vitest";
import { sha1Hex, buildSapisidHash } from "../src/auth/sapisid";

describe("sha1Hex", () => {
  it("matches the known SHA-1 vector for 'abc'", async () => {
    expect(await sha1Hex("abc")).toBe("a9993e364706816aba3e25717850c26c9cd0d89d");
  });
});

describe("buildSapisidHash", () => {
  it("formats as `${ts}_${sha1(ts + ' ' + sapisid + ' ' + origin)}`", async () => {
    const ts = 1700000000;
    const origin = "https://music.youtube.com";
    const sapisid = "SECRET";
    const expectedHash = await sha1Hex(`${ts} ${sapisid} ${origin}`);
    expect(await buildSapisidHash(sapisid, origin, ts)).toBe(`${ts}_${expectedHash}`);
  });
});
