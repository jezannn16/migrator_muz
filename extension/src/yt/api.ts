import { ytFetch } from "../auth/yt";

export interface SongCandidate {
  videoId: string;
  title: string;
  artists: string[];
  durationSeconds?: number;
}

// youtubei "Songs" search filter param.
const SONGS_PARAMS = "EgWKAQIIAWoKEAkQBRAKEAMQBA%3D%3D";

export async function searchSongs(query: string): Promise<SongCandidate[]> {
  const data = await ytFetch("search", { query, params: SONGS_PARAMS });
  return extractSongs(data);
}

// Walks the youtubei search response and pulls song renderers.
// youtubei is undocumented — selectors are validated/corrected against real output in the gate.
export function extractSongs(data: any): SongCandidate[] {
  const out: SongCandidate[] = [];
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
      const subRuns: any[] =
        cols[1]?.musicResponsiveListItemFlexColumnRenderer?.text?.runs ?? [];
      const texts = subRuns
        .filter((x) => x.text && x.text.trim() !== "•")
        .map((x) => x.text as string);
      const durText = texts.length ? texts[texts.length - 1] : "";
      const durationSeconds = parseDuration(durText);
      const artists = durationSeconds !== undefined ? texts.slice(0, -1) : texts;
      if (videoId && title) out.push({ videoId, title, artists, durationSeconds });
    }
    for (const v of Object.values(node)) if (v && typeof v === "object") stack.push(v);
  }
  return out;
}

export function parseDuration(text: string): number | undefined {
  const m = /^(\d+):(\d{2})$/.exec(text.trim());
  return m ? parseInt(m[1], 10) * 60 + parseInt(m[2], 10) : undefined;
}
