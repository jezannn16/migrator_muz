import { describe, it, expect } from "vitest";
import { normalize, ratio, scoreCandidate, bestMatch, Candidate } from "../src/engine/match";

describe("normalize", () => {
  it("lowercases and trims", () => expect(normalize("  Hello World  ")).toBe("hello world"));
  it("strips feat", () => expect(normalize("Song feat. Other")).toBe("song"));
  it("removes bracket content", () => expect(normalize("Song (Remix) [Live]")).toBe("song"));
  it("drops punctuation", () => expect(normalize("Rock'n'Roll, Baby!")).toBe("rock n roll baby"));
  it("handles empty", () => expect(normalize("")).toBe(""));
  it("keeps cyrillic", () => expect(normalize("Кино — Группа крови!")).toBe("кино группа крови"));
});

describe("ratio (difflib-compatible)", () => {
  it("identical => 1", () => expect(ratio("abc", "abc")).toBe(1));
  it("both empty => 1", () => expect(ratio("", "")).toBe(1));
  it("abcd vs abce => 0.75", () => expect(ratio("abcd", "abce")).toBeCloseTo(0.75, 5));
  it("disjoint => 0", () => expect(ratio("abc", "xyz")).toBe(0));
});

const cand = (title: string, artists: string[], dur?: number): Candidate => ({
  videoId: "v", title, artists, durationSeconds: dur,
});

describe("scoreCandidate", () => {
  it("perfect match high", () =>
    expect(scoreCandidate("Kino", "Gruppa krovi", 200, cand("Gruppa krovi", ["Kino"], 200))).toBeGreaterThan(0.95));
  it("wrong track low", () =>
    expect(scoreCandidate("Kino", "Gruppa krovi", 200, cand("Imagine", ["John Lennon"], 180))).toBeLessThan(0.5));
  it("closer duration scores higher", () => {
    const close = scoreCandidate("A", "Song", 200, cand("Song", ["A"], 200));
    const far = scoreCandidate("A", "Song", 200, cand("Song", ["A"], 260));
    expect(close).toBeGreaterThan(far);
  });
});

describe("bestMatch", () => {
  it("picks candidate above threshold", async () => {
    const search = async () => [cand("Gruppa krovi", ["Kino"], 200), cand("Other", ["X"], 100)];
    const { cand: c, score } = await bestMatch(search, "Kino", "Gruppa krovi", 200, 0.62);
    expect(c?.title).toBe("Gruppa krovi");
    expect(score).toBeGreaterThan(0.62);
  });
  it("returns null below threshold", async () => {
    const search = async () => [cand("Totally Different", ["Nobody"], 30)];
    const { cand: c } = await bestMatch(search, "Kino", "Gruppa krovi", 200, 0.62);
    expect(c).toBeNull();
  });
  it("stops after one query on great match", async () => {
    let calls = 0;
    const search = async () => { calls++; return [cand("Gruppa krovi", ["Kino"], 200)]; };
    await bestMatch(search, "Kino", "Gruppa krovi", 200, 0.62);
    expect(calls).toBe(1);
  });
});
