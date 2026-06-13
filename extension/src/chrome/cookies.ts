export async function getCookie(url: string, name: string): Promise<string | null> {
  const c = await chrome.cookies.get({ url, name });
  return c?.value ?? null;
}
