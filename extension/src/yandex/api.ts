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
