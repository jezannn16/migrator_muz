export async function sha1Hex(msg: string): Promise<string> {
  const buf = await crypto.subtle.digest("SHA-1", new TextEncoder().encode(msg));
  return [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

export async function buildSapisidHash(
  sapisid: string,
  origin: string,
  ts: number = Math.floor(Date.now() / 1000),
): Promise<string> {
  const hash = await sha1Hex(`${ts} ${sapisid} ${origin}`);
  return `${ts}_${hash}`;
}
