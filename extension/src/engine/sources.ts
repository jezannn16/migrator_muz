import {
  YaTrack,
  getLikedTracks,
  getPlaylists,
  getPlaylistTracks,
  getAllLikedAlbumTracks,
} from "../yandex/api";

export interface MigSource {
  key: string;
  playlistName: string;
  getTracks: () => Promise<YaTrack[]>;
}

export interface SourceSelection {
  likes: boolean;
  playlists: boolean;
  albums: boolean;
  likesName?: string;
}

export async function buildSources(sel: SourceSelection): Promise<MigSource[]> {
  const sources: MigSource[] = [];
  if (sel.likes) {
    sources.push({
      key: "state_likes",
      playlistName: sel.likesName?.trim() || "Yandex Likes",
      getTracks: getLikedTracks,
    });
  }
  if (sel.playlists) {
    for (const p of await getPlaylists()) {
      if (p.trackCount === 0) continue;
      sources.push({
        key: `state_pl_${p.kind}`,
        playlistName: p.title || `Playlist ${p.kind}`,
        getTracks: () => getPlaylistTracks(p.kind),
      });
    }
  }
  if (sel.albums) {
    sources.push({
      key: "state_albums",
      playlistName: "Yandex Albums",
      getTracks: getAllLikedAlbumTracks,
    });
  }
  return sources;
}
