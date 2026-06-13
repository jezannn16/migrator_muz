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

// ---------------- плейлисты ----------------

export interface YaPlaylist {
  kind: number;
  title: string;
  trackCount: number;
}

export function parsePlaylistList(data: any): YaPlaylist[] {
  return (data.result ?? []).map((p: any) => ({
    kind: p.kind,
    title: p.title ?? "",
    trackCount: p.trackCount ?? 0,
  }));
}

// Track ids of a playlist, in playlist order (NOT sorted by time).
export function parsePlaylistTrackIds(data: any): string[] {
  const tracks: any[] = data.result?.tracks ?? [];
  return tracks.map((t) => (t.albumId ? `${t.id}:${t.albumId}` : `${t.id}`));
}

export async function getPlaylists(): Promise<YaPlaylist[]> {
  const uid = await getUid();
  return parsePlaylistList(await yGet(`users/${uid}/playlists/list`));
}

export async function getPlaylistTracks(kind: number): Promise<YaTrack[]> {
  const uid = await getUid();
  const ids = parsePlaylistTrackIds(await yGet(`users/${uid}/playlists/${kind}`));
  return getTracksByIds(ids);
}

// ---------------- альбомы ----------------

export function parseLikedAlbumIds(data: any): number[] {
  return (data.result ?? []).map((a: any) => a.id ?? a.album?.id).filter((x: any) => x != null);
}

export function parseAlbumTrackIds(data: any): string[] {
  const albumId = data.result?.id;
  const volumes: any[][] = data.result?.volumes ?? [];
  const ids: string[] = [];
  for (const vol of volumes) {
    for (const t of vol) {
      ids.push(t.albumId ? `${t.id}:${t.albumId}` : albumId ? `${t.id}:${albumId}` : `${t.id}`);
    }
  }
  return ids;
}

export async function getLikedAlbumIds(): Promise<number[]> {
  const uid = await getUid();
  return parseLikedAlbumIds(await yGet(`users/${uid}/likes/albums`));
}

export async function getAlbumTracks(albumId: number): Promise<YaTrack[]> {
  const ids = parseAlbumTrackIds(await yGet(`albums/${albumId}/with-tracks`));
  return getTracksByIds(ids);
}

// All tracks across all liked albums, album by album (album order preserved).
export async function getAllLikedAlbumTracks(): Promise<YaTrack[]> {
  const albumIds = await getLikedAlbumIds();
  const out: YaTrack[] = [];
  for (const id of albumIds) out.push(...(await getAlbumTracks(id)));
  return out;
}
