import { describe, it, expect } from "vitest";
import { buildSong, parseDuration } from "../src/yt/api";

const artistRun = (text: string) => ({
  text,
  navigationEndpoint: { browseEndpoint: { browseId: "UCabc123" } },
});
const albumRun = (text: string) => ({
  text,
  navigationEndpoint: { browseEndpoint: { browseId: "MPREb_xyz" } },
});
const dot = { text: " • " };
const durRun = (text: string) => ({ text });

describe("buildSong", () => {
  it("keeps only UC artists, excludes album and duration", () => {
    const runs = [artistRun("Кино"), dot, albumRun("Чёрный альбом"), dot, durRun("4:50")];
    const song = buildSong("vid1", "Звезда", runs)!;
    expect(song.artists).toEqual(["Кино"]);
    expect(song.durationSeconds).toBe(290);
  });

  it("falls back to first text run when no UC artist", () => {
    const runs = [{ text: "Some Artist" }, dot, durRun("3:00")];
    const song = buildSong("vid2", "Title", runs)!;
    expect(song.artists).toEqual(["Some Artist"]);
    expect(song.durationSeconds).toBe(180);
  });

  it("returns null without videoId or title", () => {
    expect(buildSong(undefined, "T", [])).toBeNull();
    expect(buildSong("v", "", [])).toBeNull();
  });
});

describe("parseDuration", () => {
  it("parses m:ss", () => expect(parseDuration("3:45")).toBe(225));
  it("returns undefined for non-duration", () => expect(parseDuration("Album")).toBeUndefined());
});
