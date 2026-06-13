import { bestMatch, Candidate, SearchFn } from "./match";

export interface SourceTrack {
  id: string;
  title: string;
  artist: string;
  durationSeconds?: number;
  available: boolean;
}

export interface DoneEntry {
  status: "ok" | "miss";
  ya: string;
  yt?: string;
  videoId?: string;
  score?: number;
  reason?: string;
}

export interface MigState {
  playlistId: string | null;
  done: Record<string, DoneEntry>;
}

export interface Progress {
  phase: "idle" | "fetching" | "creating" | "matching" | "done" | "stopped" | "error";
  total: number;
  processed: number;
  matched: number;
  missed: number;
  current: string;
  playlistId: string | null;
  error?: string;
  log: string[];
  misses: { ya: string; reason: string }[];
}

export interface MigrationDeps {
  getTracks: () => Promise<SourceTrack[]>;
  search: SearchFn;
  createPlaylist: (title: string, description: string) => Promise<string>;
  addItem: (playlistId: string, videoId: string) => Promise<void>;
  loadState: () => Promise<MigState>;
  saveState: (s: MigState) => Promise<void>;
  sleep?: (ms: number) => Promise<void>;
}

export interface MigrationOpts {
  playlistName: string;
  playlistDesc?: string;
  threshold?: number;
  sleepMs?: number;
  reset?: boolean;
}

const wait = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));

async function retry<T>(fn: () => Promise<T>, log: (m: string) => void, label: string, sleep: (ms: number) => Promise<void>): Promise<T> {
  let last: unknown;
  for (let i = 0; i < 3; i++) {
    try {
      return await fn();
    } catch (e) {
      last = e;
      if (i < 2) {
        log(`  ${label}: ошибка (${(e as Error).message}); ретрай ${i + 1}/2`);
        await sleep(1000 * (i + 1));
      }
    }
  }
  throw last;
}

export async function runMigration(
  deps: MigrationDeps,
  opts: MigrationOpts,
  report: (p: Progress) => void,
  shouldStop: () => boolean = () => false,
): Promise<void> {
  const sleep = deps.sleep ?? wait;
  const threshold = opts.threshold ?? 0.62;
  const sleepMs = opts.sleepMs ?? 300;
  const p: Progress = {
    phase: "idle", total: 0, processed: 0, matched: 0, missed: 0,
    current: "", playlistId: null, log: [], misses: [],
  };
  const emit = () => report({ ...p, log: [...p.log], misses: [...p.misses] });
  const log = (m: string) => {
    p.log.push(m);
    if (p.log.length > 400) p.log = p.log.slice(-400);
    emit();
  };

  try {
    p.phase = "fetching"; emit();
    log("Выгрузка треков из Яндекса...");
    const tracks = await deps.getTracks();
    p.total = tracks.length; emit();
    log(`Всего: ${tracks.length}`);

    let state = await deps.loadState();
    if (opts.reset) state = { playlistId: null, done: {} };

    if (!state.playlistId) {
      p.phase = "creating"; emit();
      state.playlistId = await retry(
        () => deps.createPlaylist(opts.playlistName, opts.playlistDesc ?? ""),
        log, "createPlaylist", sleep,
      );
      await deps.saveState(state);
      log(`Плейлист создан: ${opts.playlistName}`);
    }
    const pid = state.playlistId;
    p.playlistId = pid;

    p.matched = Object.values(state.done).filter((v) => v.status === "ok").length;
    p.missed = Object.values(state.done).filter((v) => v.status === "miss").length;
    p.processed = Object.keys(state.done).length;
    p.phase = "matching"; emit();

    const markMiss = (id: string, ya: string, reason: string) => {
      state.done[id] = { status: "miss", ya, reason };
      p.missed++;
      p.misses.push({ ya, reason });
    };

    for (const t of tracks) {
      if (shouldStop()) {
        p.phase = "stopped"; emit();
        log("Остановлено.");
        await deps.saveState(state);
        return;
      }
      if (state.done[t.id]) continue;

      const label = `${t.artist} — ${t.title}`;
      p.current = label; emit();

      if (!t.available) {
        markMiss(t.id, label, "недоступен в Яндексе");
        p.processed = Object.keys(state.done).length; emit();
        await deps.saveState(state);
        continue;
      }

      let cand: Candidate | null = null;
      let score = 0;
      try {
        const res = await bestMatch(deps.search, t.artist, t.title, t.durationSeconds, threshold);
        cand = res.cand; score = res.score;
      } catch (e) {
        markMiss(t.id, label, `ошибка поиска: ${(e as Error).message}`);
        p.processed = Object.keys(state.done).length; emit();
        await deps.saveState(state);
        continue;
      }

      if (cand) {
        try {
          await retry(() => deps.addItem(pid, cand!.videoId), log, "add", sleep);
        } catch (e) {
          markMiss(t.id, label, `ошибка добавления: ${(e as Error).message}`);
          p.processed = Object.keys(state.done).length; emit();
          await deps.saveState(state);
          await sleep(sleepMs);
          continue;
        }
        state.done[t.id] = {
          status: "ok", ya: label,
          yt: `${cand.artists.join(", ")} — ${cand.title}`,
          videoId: cand.videoId, score: Math.round(score * 1000) / 1000,
        };
        p.matched++;
        log(`OK ${score.toFixed(2)}  ${label}`);
      } else {
        markMiss(t.id, label, `низкая оценка ${score.toFixed(2)}`);
        log(`MISS ${score.toFixed(2)}  ${label}`);
      }

      p.processed = Object.keys(state.done).length; emit();
      await deps.saveState(state);
      await sleep(sleepMs);
    }

    await deps.saveState(state);
    p.phase = "done"; p.current = ""; emit();
    log(`Готово. Найдено: ${p.matched}, не найдено: ${p.missed}, всего: ${p.total}`);
  } catch (e) {
    p.phase = "error"; p.error = (e as Error).message; emit();
    log(`ОШИБКА: ${(e as Error).message}`);
  }
}
