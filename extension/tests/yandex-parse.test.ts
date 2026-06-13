import { describe, it, expect } from "vitest";
import {
  parsePlaylistList,
  parsePlaylistTrackIds,
  parseLikedAlbumIds,
  parseAlbumTrackIds,
} from "../src/yandex/api";

describe("parsePlaylistList", () => {
  it("maps kind/title/trackCount", () => {
    const data = { result: [{ kind: 3, title: "Любимое", trackCount: 12 }, { kind: 1001, title: "Рок" }] };
    expect(parsePlaylistList(data)).toEqual([
      { kind: 3, title: "Любимое", trackCount: 12 },
      { kind: 1001, title: "Рок", trackCount: 0 },
    ]);
  });
});

describe("parsePlaylistTrackIds", () => {
  it("keeps playlist order as id:albumId", () => {
    const data = { result: { tracks: [{ id: 10, albumId: 100 }, { id: 20, albumId: 200 }] } };
    expect(parsePlaylistTrackIds(data)).toEqual(["10:100", "20:200"]);
  });
  it("handles missing albumId", () => {
    expect(parsePlaylistTrackIds({ result: { tracks: [{ id: 5 }] } })).toEqual(["5"]);
  });
});

describe("parseLikedAlbumIds", () => {
  it("reads album ids (direct or nested)", () => {
    expect(parseLikedAlbumIds({ result: [{ id: 7 }, { album: { id: 9 } }] })).toEqual([7, 9]);
  });
});

describe("parseAlbumTrackIds", () => {
  it("flattens volumes and tags album id", () => {
    const data = { result: { id: 500, volumes: [[{ id: 1 }, { id: 2 }], [{ id: 3, albumId: 500 }]] } };
    expect(parseAlbumTrackIds(data)).toEqual(["1:500", "2:500", "3:500"]);
  });
});
