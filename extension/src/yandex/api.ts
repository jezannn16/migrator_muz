import { loadYandexToken } from "../auth/yandex";

const BASE = "https://api.music.yandex.net";

async function yGet(path: string): Promise<any> {
  const token = await loadYandexToken();
  if (!token) throw new Error("Не выполнен вход в Яндекс.");
  const res = await fetch(`${BASE}/${path}`, {
    headers: { Authorization: `OAuth ${token}` },
  });
  if (!res.ok) throw new Error(`yandex ${path} -> HTTP ${res.status}`);
  return res.json();
}

export async function getUid(): Promise<number> {
  const data = await yGet("account/status");
  return data.result.account.uid;
}

export async function getLikesCount(): Promise<number> {
  const uid = await getUid();
  const data = await yGet(`users/${uid}/likes/tracks`);
  return (data.result.library.tracks ?? []).length;
}

export interface YaTrack {
  id: string;
  title: string;
  artist: string;
  durationSeconds?: number;
  available: boolean;
}

// Track ids of liked tracks, sorted oldest -> newest (order they were added).
export async function getLikedTrackIds(): Promise<string[]> {
  const uid = await getUid();
  const data = await yGet(`users/${uid}/likes/tracks`);
  const arr: any[] = data.result.library.tracks ?? [];
  arr.sort((a, b) => String(a.timestamp ?? "").localeCompare(String(b.timestamp ?? "")));
  return arr.map((t) => (t.albumId ? `${t.id}:${t.albumId}` : `${t.id}`));
}

export async function getTracksByIds(ids: string[]): Promise<YaTrack[]> {
  const out: YaTrack[] = [];
  for (let i = 0; i < ids.length; i += 50) {
    const chunk = ids.slice(i, i + 50);
    const data = await yGet(`tracks?track-ids=${chunk.join(",")}`);
    for (const t of data.result ?? []) {
      out.push({
        id: String(t.id),
        title: t.title ?? "",
        artist: (t.artists ?? []).map((a: any) => a.name).join(", "),
        durationSeconds: t.durationMs ? Math.round(t.durationMs / 1000) : undefined,
        available: t.available !== false,
      });
    }
  }
  return out;
}

export async function getLikedTracks(): Promise<YaTrack[]> {
  return getTracksByIds(await getLikedTrackIds());
}
