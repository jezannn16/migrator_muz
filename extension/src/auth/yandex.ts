const CLIENT_ID = "23cabbbdc6cd418abb4b39c32c41195d";
const TOKEN_KEY = "yandex_token";

export function parseYandexToken(hash: string): string | null {
  const m = /access_token=([^&]+)/.exec(hash);
  return m ? decodeURIComponent(m[1]) : null;
}

export function yandexOAuthUrl(): string {
  return `https://oauth.yandex.ru/authorize?response_type=token&client_id=${CLIENT_ID}`;
}

export async function saveYandexToken(token: string): Promise<void> {
  await chrome.storage.local.set({ [TOKEN_KEY]: token });
}

export async function loadYandexToken(): Promise<string | null> {
  const r = await chrome.storage.local.get(TOKEN_KEY);
  return (r[TOKEN_KEY] as string) ?? null;
}

export async function yandexIsLoggedIn(): Promise<boolean> {
  return (await loadYandexToken()) !== null;
}
