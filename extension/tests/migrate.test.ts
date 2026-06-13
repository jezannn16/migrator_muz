import { describe, it, expect } from "vitest";
import { runMigration, MigState, SourceTrack, Progress, MigrationDeps } from "../src/engine/migrate";
import { Candidate } from "../src/engine/match";

const track = (id: string, title: string, artist: string, available = true): SourceTrack => ({
  id, title, artist, durationSeconds: 200, available,
});
const cand = (title: string, artist: string): Candidate => ({
  videoId: "vid_" + title, title, artists: [artist], durationSeconds: 200,
});

interface Harness {
  added: string[];
  created: string[];
  liked?: never;
  deps: MigrationDeps;
  last: () => Progress;
}

function harness(
  tracks: SourceTrack[],
  matches: Record<string, Candidate>,
  opts: { failCreate?: number; initial?: MigState } = {},
): Harness {
  let state: MigState = opts.initial ?? { playlistId: null, done: {} };
  let failCreate = opts.failCreate ?? 0;
  const added: string[] = [];
  const created: string[] = [];
  let last: Progress = {} as Progress;
  const deps: MigrationDeps = {
    getTracks: async () => tracks,
    search: async (q: string) => {
      const hit = Object.entries(matches).find(([t]) => q.toLowerCase().includes(t.toLowerCase()));
      return hit ? [hit[1]] : [];
    },
    createPlaylist: async (title: string) => {
      if (failCreate > 0) { failCreate--; throw new Error("HTTP 400 Sorry"); }
      created.push(title);
      return "PLID";
    },
    addItem: async (_pid: string, vid: string) => { added.push(vid); },
    loadState: async () => state,
    saveState: async (s: MigState) => { state = JSON.parse(JSON.stringify(s)); },
    sleep: async () => {},
  };
  return { added, created, deps, last: () => last, get _state() { return state; } } as any;
}

async function run(h: Harness, opts: any = {}) {
  let last: Progress = {} as Progress;
  await runMigration(h.deps, { playlistName: "Yandex Likes", threshold: 0.62, sleepMs: 0, ...opts },
    (p) => { last = p; });
  return last;
}

describe("runMigration", () => {
  it("adds matched tracks in the given order", async () => {
    const h = harness(
      [track("1", "Alpha", "A"), track("2", "Beta", "B"), track("3", "Gamma", "G")],
      { Alpha: cand("Alpha", "A"), Beta: cand("Beta", "B"), Gamma: cand("Gamma", "G") },
    );
    const p = await run(h);
    expect(h.added).toEqual(["vid_Alpha", "vid_Beta", "vid_Gamma"]);
    expect(h.created).toEqual(["Yandex Likes"]);
    expect(p.matched).toBe(3);
    expect(p.phase).toBe("done");
  });

  it("marks miss when no match", async () => {
    const h = harness(
      [track("1", "Known", "A"), track("2", "Unfindable", "B")],
      { Known: cand("Known", "A") },
    );
    const p = await run(h);
    expect(h.added).toEqual(["vid_Known"]);
    expect(p.matched).toBe(1);
    expect(p.missed).toBe(1);
    expect(p.misses.some((m) => m.ya.includes("Unfindable"))).toBe(true);
  });

  it("skips unavailable tracks", async () => {
    const h = harness([track("1", "Gone", "A", false)], { Gone: cand("Gone", "A") });
    const p = await run(h);
    expect(h.added).toEqual([]);
    expect(p.missed).toBe(1);
  });

  it("resume skips done and does not recreate playlist", async () => {
    const h = harness(
      [track("1", "Alpha", "A"), track("2", "Beta", "B")],
      { Alpha: cand("Alpha", "A"), Beta: cand("Beta", "B") },
      { initial: { playlistId: "PLID", done: { "1": { status: "ok", ya: "A — Alpha" } } } },
    );
    await run(h);
    expect(h.added).toEqual(["vid_Beta"]);
    expect(h.created).toEqual([]);
  });

  it("retries transient create failure", async () => {
    const h = harness([track("1", "Alpha", "A")], { Alpha: cand("Alpha", "A") }, { failCreate: 1 });
    const p = await run(h);
    expect(h.created).toEqual(["Yandex Likes"]);
    expect(h.added).toEqual(["vid_Alpha"]);
    expect(p.phase).toBe("done");
  });

  it("halts on stop", async () => {
    const h = harness(
      [track("1", "Alpha", "A"), track("2", "Beta", "B")],
      { Alpha: cand("Alpha", "A"), Beta: cand("Beta", "B") },
    );
    let last: Progress = {} as Progress;
    await runMigration(h.deps, { playlistName: "Yandex Likes", sleepMs: 0 },
      (p) => { last = p; }, () => true);
    expect(h.added).toEqual([]);
    expect(last.phase).toBe("stopped");
  });
});
