import { getCookie } from "../chrome/cookies";
import { buildSapisidHash } from "./sapisid";

const ORIGIN = "https://music.youtube.com";

export const YT_CONTEXT = {
  client: { clientName: "WEB_REMIX", clientVersion: "1.20240522.01.00", hl: "en" },
};

export async function getSapisid(): Promise<string | null> {
  return (await getCookie(ORIGIN, "SAPISID")) ?? (await getCookie(ORIGIN, "__Secure-3PAPISID"));
}

export async function ytIsLoggedIn(): Promise<boolean> {
  return (await getSapisid()) !== null;
}

export async function ytFetch(endpoint: string, body: Record<string, unknown>): Promise<any> {
  const sapisid = await getSapisid();
  if (!sapisid) throw new Error("Не выполнен вход в music.youtube.com в этом браузере.");
  const auth = "SAPISIDHASH " + (await buildSapisidHash(sapisid, ORIGIN));
  const res = await fetch(`${ORIGIN}/youtubei/v1/${endpoint}?prettyPrint=false`, {
    method: "POST",
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      Authorization: auth,
      "X-Goog-AuthUser": "0",
      Origin: ORIGIN,
      "X-Origin": ORIGIN,
    },
    body: JSON.stringify({ context: YT_CONTEXT, ...body }),
  });
  if (!res.ok) throw new Error(`youtubei ${endpoint} -> HTTP ${res.status}`);
  return res.json();
}
