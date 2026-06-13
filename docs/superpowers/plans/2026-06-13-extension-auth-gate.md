# Extension Auth Gate — Implementation Plan (Plan 1 of 4)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up the Chrome/Edge MV3 TypeScript extension skeleton and prove the load-bearing assumption — that the extension can make authenticated requests to YouTube Music (youtubei) via live-session cookies + SAPISIDHASH, and obtain a Yandex token via OAuth redirect-capture.

**Architecture:** Vite + @crxjs/vite-plugin builds an MV3 extension. Pure logic (hashing, parsing, API wrappers) is split from Chrome glue so it can be unit-tested with Vitest. A throwaway "Auth Test" page exercises both auth paths in a real browser — this is the project gate.

**Tech Stack:** TypeScript, Vite, @crxjs/vite-plugin, Vitest, Chrome MV3 APIs (`cookies`, `storage`, `tabs`).

**Spec:** `docs/superpowers/specs/2026-06-13-ytmusic-migrator-extension-design.md`

---

## File Structure

```
extension/
  package.json
  tsconfig.json
  vite.config.ts
  src/
    manifest.ts              # MV3 manifest (typed, via crxjs)
    chrome/cookies.ts        # thin wrapper over chrome.cookies (mockable)
    auth/sapisid.ts          # SHA-1 hex + SAPISIDHASH builder (pure)
    auth/yt.ts               # authorized youtubei fetch factory + isLoggedIn
    auth/yandex.ts           # token storage + parseYandexToken (pure) + login flow
    yt/api.ts                # youtubei wrappers used for the gate (search)
    yandex/api.ts            # api.music.yandex.net wrappers (account uid, likes count)
    content/yandex-oauth.ts  # content script: read #access_token on redirect page
    background/index.ts       # service worker: message routing for Yandex login
    ui/auth-test.html
    ui/auth-test.ts          # two buttons: test YT, test Yandex
  tests/
    sapisid.test.ts
    cookies.test.ts
    yandex-token.test.ts
```

---

### Task 1: Scaffold the extension project

**Files:**
- Create: `extension/package.json`
- Create: `extension/tsconfig.json`
- Create: `extension/vite.config.ts`
- Create: `extension/src/manifest.ts`

- [ ] **Step 1: Create `extension/package.json`**

```json
{
  "name": "ymusic-migrator-extension",
  "version": "0.0.1",
  "private": true,
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "vite build",
    "test": "vitest run"
  },
  "devDependencies": {
    "@crxjs/vite-plugin": "^2.0.0",
    "@types/chrome": "^0.0.268",
    "typescript": "^5.4.0",
    "vite": "^5.2.0",
    "vitest": "^1.6.0"
  }
}
```

- [ ] **Step 2: Create `extension/tsconfig.json`**

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "ESNext",
    "moduleResolution": "Bundler",
    "lib": ["ES2022", "DOM"],
    "types": ["chrome", "vitest/globals"],
    "strict": true,
    "skipLibCheck": true,
    "noEmit": true
  },
  "include": ["src", "tests"]
}
```

- [ ] **Step 3: Create `extension/src/manifest.ts`**

```ts
import { defineManifest } from "@crxjs/vite-plugin";

export default defineManifest({
  manifest_version: 3,
  name: "Yandex → YT Music Migrator",
  version: "0.0.1",
  permissions: ["cookies", "storage", "tabs"],
  host_permissions: [
    "https://music.youtube.com/*",
    "https://api.music.yandex.net/*",
    "https://oauth.yandex.ru/*",
    "https://*.music.yandex.ru/*",
  ],
  background: { service_worker: "src/background/index.ts", type: "module" },
  action: { default_title: "Yandex → YT Music" },
  content_scripts: [
    {
      matches: ["https://music.yandex.ru/*", "https://*.music.yandex.ru/*"],
      js: ["src/content/yandex-oauth.ts"],
      run_at: "document_start",
    },
  ],
  web_accessible_resources: [
    { resources: ["src/ui/auth-test.html"], matches: ["<all_urls>"] },
  ],
});
```

- [ ] **Step 4: Create `extension/vite.config.ts`**

```ts
import { defineConfig } from "vite";
import { crx } from "@crxjs/vite-plugin";
import manifest from "./src/manifest";

export default defineConfig({
  plugins: [crx({ manifest })],
  test: { environment: "jsdom", globals: true },
});
```

- [ ] **Step 5: Install and verify build**

Run: `cd extension && npm install && npm run build`
Expected: `dist/` produced with `manifest.json`, no TypeScript errors.

- [ ] **Step 6: Commit**

```bash
git add extension/package.json extension/tsconfig.json extension/vite.config.ts extension/src/manifest.ts
git commit -m "chore(ext): scaffold MV3 TypeScript extension (vite + crxjs)"
```

---

### Task 2: SHA-1 hex helper (TDD with known vector)

**Files:**
- Create: `extension/src/auth/sapisid.ts`
- Test: `extension/tests/sapisid.test.ts`

- [ ] **Step 1: Write the failing test**

```ts
import { describe, it, expect } from "vitest";
import { sha1Hex, buildSapisidHash } from "../src/auth/sapisid";

describe("sha1Hex", () => {
  it("matches the known SHA-1 vector for 'abc'", async () => {
    expect(await sha1Hex("abc")).toBe("a9993e364706816aba3e25717850c26c9cd0d89c");
  });
});

describe("buildSapisidHash", () => {
  it("formats as `${ts}_${sha1(ts + ' ' + sapisid + ' ' + origin)}`", async () => {
    const ts = 1700000000;
    const origin = "https://music.youtube.com";
    const sapisid = "SECRET";
    const expectedHash = await sha1Hex(`${ts} ${sapisid} ${origin}`);
    expect(await buildSapisidHash(sapisid, origin, ts)).toBe(`${ts}_${expectedHash}`);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd extension && npx vitest run tests/sapisid.test.ts`
Expected: FAIL — cannot find module `../src/auth/sapisid`.

- [ ] **Step 3: Write minimal implementation**

```ts
// extension/src/auth/sapisid.ts
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd extension && npx vitest run tests/sapisid.test.ts`
Expected: PASS (both tests).

- [ ] **Step 5: Commit**

```bash
git add extension/src/auth/sapisid.ts extension/tests/sapisid.test.ts
git commit -m "feat(ext): SAPISIDHASH builder with SHA-1 (TDD)"
```

---

### Task 3: Chrome cookies wrapper (TDD with mock)

**Files:**
- Create: `extension/src/chrome/cookies.ts`
- Test: `extension/tests/cookies.test.ts`

- [ ] **Step 1: Write the failing test**

```ts
import { describe, it, expect, vi, beforeEach } from "vitest";
import { getCookie } from "../src/chrome/cookies";

beforeEach(() => {
  (globalThis as any).chrome = {
    cookies: { get: vi.fn(async ({ name }: { name: string }) =>
      name === "SAPISID" ? { value: "SECRET" } : null) },
  };
});

describe("getCookie", () => {
  it("returns the cookie value when present", async () => {
    expect(await getCookie("https://music.youtube.com", "SAPISID")).toBe("SECRET");
  });
  it("returns null when cookie missing", async () => {
    expect(await getCookie("https://music.youtube.com", "NOPE")).toBeNull();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd extension && npx vitest run tests/cookies.test.ts`
Expected: FAIL — cannot find module `../src/chrome/cookies`.

- [ ] **Step 3: Write minimal implementation**

```ts
// extension/src/chrome/cookies.ts
export async function getCookie(url: string, name: string): Promise<string | null> {
  const c = await chrome.cookies.get({ url, name });
  return c?.value ?? null;
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd extension && npx vitest run tests/cookies.test.ts`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add extension/src/chrome/cookies.ts extension/tests/cookies.test.ts
git commit -m "feat(ext): chrome.cookies wrapper (TDD)"
```

---

### Task 4: Authorized youtubei fetch + search wrapper

**Files:**
- Create: `extension/src/auth/yt.ts`
- Create: `extension/src/yt/api.ts`

> Note: these call live Chrome APIs and the network, so they are verified in the manual gate (Task 8), not unit-tested.

- [ ] **Step 1: Write `extension/src/auth/yt.ts`**

```ts
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
```

- [ ] **Step 2: Write `extension/src/yt/api.ts` (minimal search for the gate)**

```ts
import { ytFetch } from "../auth/yt";

export interface SongCandidate {
  videoId: string;
  title: string;
  artists: string[];
  durationSeconds?: number;
}

// Music search filter param for "Songs"
const SONGS_PARAMS = "EgWKAQIIAWoKEAkQBRAKEAMQBA%3D%3D";

export async function searchSongs(query: string): Promise<SongCandidate[]> {
  const data = await ytFetch("search", { query, params: SONGS_PARAMS });
  return extractSongs(data);
}

// Walks the youtubei search response and pulls song renderers.
export function extractSongs(data: any): SongCandidate[] {
  const out: SongCandidate[] = [];
  const stack = [data];
  while (stack.length) {
    const node = stack.pop();
    if (!node || typeof node !== "object") continue;
    const r = node.musicResponsiveListItemRenderer;
    if (r) {
      const videoId =
        r.playlistItemData?.videoId ??
        r.overlay?.musicItemThumbnailOverlayRenderer?.content?.musicPlayButtonRenderer
          ?.playNavigationEndpoint?.watchEndpoint?.videoId;
      const cols = r.flexColumns ?? [];
      const title =
        cols[0]?.musicResponsiveListItemFlexColumnRenderer?.text?.runs?.[0]?.text ?? "";
      const subruns =
        cols[1]?.musicResponsiveListItemFlexColumnRenderer?.text?.runs ?? [];
      const artists = subruns(subruns).filter(Boolean);
      const durText = artists.length ? (subruns(subruns).at(-1) ?? "") : "";
      if (videoId && title) out.push({ videoId, title, artists, durationSeconds: parseDuration(durText) });
    }
    for (const v of Object.values(node)) if (v && typeof v === "object") stack.push(v);
  }
  return out;
}

function subruns(runs: any[]): string[] {
  return runs.filter((r) => r.text && r.text !== " • ").map((r) => r.text);
}

export function parseDuration(text: string): number | undefined {
  const m = /^(\d+):(\d{2})$/.exec(text.trim());
  return m ? parseInt(m[1], 10) * 60 + parseInt(m[2], 10) : undefined;
}
```

> `extractSongs` parsing is fragile by nature (youtubei is undocumented). The gate (Task 8) prints raw + parsed output so the engineer can correct selectors against the real response before Plan 2.

- [ ] **Step 3: Commit**

```bash
git add extension/src/auth/yt.ts extension/src/yt/api.ts
git commit -m "feat(ext): authorized youtubei fetch + song search wrapper"
```

---

### Task 5: Yandex token parsing (TDD) + storage

**Files:**
- Create: `extension/src/auth/yandex.ts`
- Test: `extension/tests/yandex-token.test.ts`

- [ ] **Step 1: Write the failing test**

```ts
import { describe, it, expect } from "vitest";
import { parseYandexToken } from "../src/auth/yandex";

describe("parseYandexToken", () => {
  it("extracts access_token from a redirect hash", () => {
    const hash = "#access_token=AQAA123&token_type=bearer&expires_in=31536000";
    expect(parseYandexToken(hash)).toBe("AQAA123");
  });
  it("url-decodes the token", () => {
    expect(parseYandexToken("#access_token=ab%2Bcd&x=1")).toBe("ab+cd");
  });
  it("returns null when no token present", () => {
    expect(parseYandexToken("#error=access_denied")).toBeNull();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd extension && npx vitest run tests/yandex-token.test.ts`
Expected: FAIL — cannot find module `../src/auth/yandex`.

- [ ] **Step 3: Write minimal implementation**

```ts
// extension/src/auth/yandex.ts
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd extension && npx vitest run tests/yandex-token.test.ts`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add extension/src/auth/yandex.ts extension/tests/yandex-token.test.ts
git commit -m "feat(ext): Yandex token parse + storage (TDD)"
```

---

### Task 6: Yandex OAuth flow glue (content script + background)

**Files:**
- Create: `extension/src/content/yandex-oauth.ts`
- Create: `extension/src/background/index.ts`

> Glue across Chrome contexts — verified in the manual gate (Task 8).

- [ ] **Step 1: Write `extension/src/content/yandex-oauth.ts`**

```ts
import { parseYandexToken } from "../auth/yandex";

// Runs on music.yandex.ru pages (document_start). If the URL fragment carries an
// OAuth token (redirect from oauth.yandex.ru), forward it to the background worker.
const token = parseYandexToken(location.hash);
if (token) {
  chrome.runtime.sendMessage({ type: "YANDEX_TOKEN", token });
}
```

- [ ] **Step 2: Write `extension/src/background/index.ts`**

```ts
import { saveYandexToken, yandexOAuthUrl } from "../auth/yandex";

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (msg?.type === "YANDEX_TOKEN" && typeof msg.token === "string") {
    saveYandexToken(msg.token).then(() => sendResponse({ ok: true }));
    return true; // async response
  }
  if (msg?.type === "YANDEX_LOGIN") {
    chrome.tabs.create({ url: yandexOAuthUrl() });
    sendResponse({ ok: true });
    return false;
  }
  return false;
});
```

- [ ] **Step 3: Build to verify it compiles**

Run: `cd extension && npm run build`
Expected: build succeeds, `dist/` updated.

- [ ] **Step 4: Commit**

```bash
git add extension/src/content/yandex-oauth.ts extension/src/background/index.ts
git commit -m "feat(ext): Yandex OAuth redirect-capture (content script + background)"
```

---

### Task 7: Yandex API wrappers (account uid + likes count)

**Files:**
- Create: `extension/src/yandex/api.ts`

> Network-bound — verified in the manual gate (Task 8).

- [ ] **Step 1: Write `extension/src/yandex/api.ts`**

```ts
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
```

- [ ] **Step 2: Build to verify it compiles**

Run: `cd extension && npm run build`
Expected: build succeeds.

- [ ] **Step 3: Commit**

```bash
git add extension/src/yandex/api.ts
git commit -m "feat(ext): Yandex API wrappers (uid + likes count)"
```

---

### Task 8: Auth Test page + MANUAL GATE

**Files:**
- Create: `extension/src/ui/auth-test.html`
- Create: `extension/src/ui/auth-test.ts`

This page is the project gate. It must run in a real Chrome/Edge with the user logged into both services.

- [ ] **Step 1: Write `extension/src/ui/auth-test.html`**

```html
<!doctype html>
<html lang="ru">
<head><meta charset="utf-8"><title>Auth Test</title></head>
<body style="font-family:sans-serif;max-width:680px;margin:40px auto">
  <h1>Проверка авторизации</h1>
  <button id="ytBtn">Тест YouTube (search)</button>
  <button id="yaLoginBtn">Войти через Яндекс</button>
  <button id="yaBtn">Тест Яндекс (лайки)</button>
  <pre id="out" style="background:#111;color:#0f0;padding:12px;white-space:pre-wrap"></pre>
  <script type="module" src="./auth-test.ts"></script>
</body>
</html>
```

- [ ] **Step 2: Write `extension/src/ui/auth-test.ts`**

```ts
import { searchSongs } from "../yt/api";
import { ytIsLoggedIn } from "../auth/yt";
import { getLikesCount, getUid } from "../yandex/api";
import { yandexIsLoggedIn } from "../auth/yandex";

const out = document.getElementById("out")!;
const log = (x: unknown) => (out.textContent += (typeof x === "string" ? x : JSON.stringify(x, null, 2)) + "\n");

document.getElementById("ytBtn")!.addEventListener("click", async () => {
  try {
    log("YT logged in: " + (await ytIsLoggedIn()));
    const res = await searchSongs("kino gruppa krovi");
    log(`YT search -> ${res.length} songs`);
    log(res.slice(0, 3));
  } catch (e) { log("YT ERROR: " + (e as Error).message); }
});

document.getElementById("yaLoginBtn")!.addEventListener("click", () => {
  chrome.runtime.sendMessage({ type: "YANDEX_LOGIN" });
  log("Открыл вход Яндекса в новой вкладке. Залогинься, потом нажми «Тест Яндекс».");
});

document.getElementById("yaBtn")!.addEventListener("click", async () => {
  try {
    log("Yandex logged in: " + (await yandexIsLoggedIn()));
    log("uid: " + (await getUid()));
    log("likes: " + (await getLikesCount()));
  } catch (e) { log("Yandex ERROR: " + (e as Error).message); }
});
```

- [ ] **Step 3: Build**

Run: `cd extension && npm run build`
Expected: `dist/` contains the auth-test page.

- [ ] **Step 4: Load unpacked + run the GATE manually**

1. Chrome/Edge → `chrome://extensions` → enable Developer mode → Load unpacked → select `extension/dist`.
2. Open the extension's `auth-test.html` (via the extension details → or navigate to `chrome-extension://<id>/src/ui/auth-test.html`).
3. Ensure you are logged into `https://music.youtube.com` in this browser.
4. Click **Тест YouTube** → expect `YT logged in: true` and a non-zero song count with plausible titles.
5. Click **Войти через Яндекс** → log in → tab captures token → click **Тест Яндекс** → expect a uid and a non-zero likes count.

**GATE PASS CRITERIA:** both calls return real data (YT search list + Yandex likes count). 

**IF GATE FAILS:**
- YT 400/401 → the cookie/SAPISIDHASH approach does not work from an extension; STOP and revise the architecture (fallback: keep header-paste, or revisit Data API). Do not proceed to Plan 2.
- `extractSongs` returns 0 but raw response has results → fix selectors in `yt/api.ts` against the logged raw JSON, re-run.
- Yandex error → check token capture (content script matches, hash parsing) and `account/status` shape.

- [ ] **Step 5: Record the gate result**

Append outcome to `docs/superpowers/specs/2026-06-13-ytmusic-migrator-extension-design.md` under a new `## Gate result` heading (pass/fail + any selector corrections). Commit.

```bash
git add extension/src/ui/ docs/
git commit -m "feat(ext): auth-test page; record auth gate result"
```

---

## Self-Review

**Spec coverage (Plan 1 scope = spec Phase 1):**
- Zero-paste YT auth (cookies + SAPISIDHASH) → Tasks 2–4, gated in Task 8. ✓
- Zero-paste Yandex auth (OAuth redirect-capture) → Tasks 5–7, gated in Task 8. ✓
- MV3 scaffold, host permissions, no server → Task 1. ✓
- Engine/sources/UI/migration → deferred to Plans 2–4 (correctly out of scope here). ✓

**Placeholder scan:** No TBD/TODO. `extractSongs` flagged as fragile-by-design with a concrete correction path in the gate. ✓

**Type consistency:** `getCookie`, `buildSapisidHash(sapisid, origin, ts?)`, `ytFetch(endpoint, body)`, `SongCandidate`, `parseYandexToken`, `loadYandexToken` used consistently across tasks. ✓

## Next plans (after gate passes)

- **Plan 2:** matching engine on TS (port `normalize`/`scoreCandidate`/`bestMatch`, TDD) + likes end-to-end in a UI tab (create playlist, search, add, progress, resumable `chrome.storage.local` state, transient-400 retry).
- **Plan 3:** playlists + albums sources.
- **Plan 4:** landing page + sideload packaging, then Chrome Web Store submission.
