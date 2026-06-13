import type { MigState } from "../engine/migrate";

const empty = (): MigState => ({ playlistId: null, done: {} });

export async function loadMigState(key: string): Promise<MigState> {
  const r = await chrome.storage.local.get(key);
  return (r[key] as MigState) ?? empty();
}

export async function saveMigState(key: string, s: MigState): Promise<void> {
  await chrome.storage.local.set({ [key]: s });
}

export async function resetMigState(key: string): Promise<void> {
  await chrome.storage.local.remove(key);
}
