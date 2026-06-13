import { ytFetch } from "../auth/yt";
import type { Candidate } from "../engine/match";

// youtubei "Songs" search filter param.
const SONGS_PARAMS = "EgWKAQIIAWoKEAkQBRAKEAMQBA%3D%3D";

export async function searchSongs(query: string): Promise<Candidate[]> {
  const data = await ytFetch("search", { query, params: SONGS_PARAMS });
  return extractSongs(data);
}

// Walks the youtubei search response and pulls song renderers.
// Subtitle runs look like: Artist(UC…) • Album(MPRE…) • m:ss
//   - artists: runs whose browseId starts with "UC"
//   - duration: the plain "m:ss" run (no endpoint)
//   - album excluded (browseId starts with "MPRE")
export function extractSongs(data: any): Candidate[] {
  const out: Candidate[] = [];
  const stack = [data];
  while (stack.length) {
    const node = stack.pop();
    if (!node || typeof node !== "object") continue;
    const r = (node as any).musicResponsiveListItemRenderer;
    if (r) {
      const videoId =
        r.playlistItemData?.videoId ??
        r.overlay?.musicItemThumbnailOverlayRenderer?.content?.musicPlayButtonRenderer
          ?.playNavigationEndpoint?.watchEndpoint?.videoId;
      const cols = r.flexColumns ?? [];
      const title =
        cols[0]?.musicResponsiveListItemFlexColumnRenderer?.text?.runs?.[0]?.text ?? "";
      const runs: any[] = cols[1]?.musicResponsiveListItemFlexColumnRenderer?.text?.runs ?? [];
      const song = buildSong(videoId, title, runs);
      if (song) out.push(song);
    }
    for (const v of Object.values(node)) if (v && typeof v === "object") stack.push(v);
  }
  return out;
}

export function buildSong(videoId: string | undefined, title: string, runs: any[]): Candidate | null {
  if (!videoId || !title) return null;
  const browseId = (run: any): string => run?.navigationEndpoint?.browseEndpoint?.browseId ?? "";
  let artists = runs.filter((r) => browseId(r).startsWith("UC")).map((r) => r.text as string);
  const durRun = runs.find((r) => /^\d+:\d{2}$/.test((r.text ?? "").trim()));
  const durationSeconds = durRun ? parseDuration(durRun.text) : undefined;
  if (artists.length === 0) {
    const first = runs.find(
      (r) => r.text && r.text.trim() && r.text.trim() !== "•" && !/^\d+:\d{2}$/.test(r.text.trim()),
    );
    if (first) artists = [first.text];
  }
  return { videoId, title, artists, durationSeconds };
}

export function parseDuration(text: string): number | undefined {
  const m = /^(\d+):(\d{2})$/.exec(text.trim());
  return m ? parseInt(m[1], 10) * 60 + parseInt(m[2], 10) : undefined;
}

export async function createPlaylist(title: string, description: string, privacy = "PRIVATE"): Promise<string> {
  const data = await ytFetch("playlist/create", {
    title,
    description,
    privacyStatus: privacy,
  });
  const pid = data.playlistId ?? data.id;
  if (!pid) throw new Error("createPlaylist: нет playlistId в ответе");
  return pid;
}

export async function addPlaylistItem(playlistId: string, videoId: string): Promise<void> {
  await ytFetch("browse/edit_playlist", {
    playlistId,
    actions: [{ action: "ACTION_ADD_VIDEO", addedVideoId: videoId }],
  });
}
