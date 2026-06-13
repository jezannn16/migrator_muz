import { ytIsLoggedIn } from "../auth/yt";
import { yandexIsLoggedIn } from "../auth/yandex";
import { searchSongs, createPlaylist, addPlaylistItem } from "../yt/api";
import { loadMigState, saveMigState } from "../storage/state";
import { runMigration, MigrationDeps, Progress } from "../engine/migrate";
import { buildSources } from "../engine/sources";

const $ = (id: string) => document.getElementById(id)!;
let stopFlag = false;
let accMisses: { ya: string; reason: string }[] = [];
let lastProgress: Progress | null = null;
const summary: string[] = [];

async function refreshAuth() {
  const yt = await ytIsLoggedIn();
  const ya = await yandexIsLoggedIn();
  $("ytStatus").textContent = "YouTube: " + (yt ? "вход есть ✓" : "не выполнен");
  $("yaStatus").textContent = "Яндекс: " + (ya ? "вход есть ✓" : "не выполнен");
  const ready = yt && ya;
  $("authBadge").textContent = ready ? "готово" : "нужен вход";
  $("authBadge").className = ready ? "badge ok" : "badge";
  ($("start") as HTMLButtonElement).disabled = !ready;
  return ready;
}

$("yaLogin").addEventListener("click", () => {
  chrome.runtime.sendMessage({ type: "YANDEX_LOGIN" });
  $("startMsg").textContent = "Открыл вход Яндекса. Залогинься, вернись и нажми «Перенести».";
});

$("thr").addEventListener("input", (e) => {
  $("thrVal").textContent = (e.target as HTMLInputElement).value;
});

$("stop").addEventListener("click", () => {
  stopFlag = true;
  $("stop").textContent = "Останавливаю…";
});

$("start").addEventListener("click", async () => {
  if (!(await refreshAuth())) {
    $("startMsg").textContent = "Сначала вход в оба сервиса.";
    return;
  }
  const sel = {
    likes: ($("selLikes") as HTMLInputElement).checked,
    playlists: ($("selPlaylists") as HTMLInputElement).checked,
    albums: ($("selAlbums") as HTMLInputElement).checked,
    likesName: ($("plName") as HTMLInputElement).value,
  };
  if (!sel.likes && !sel.playlists && !sel.albums) {
    $("startMsg").textContent = "Выбери хотя бы один источник.";
    return;
  }

  stopFlag = false;
  accMisses = [];
  summary.length = 0;
  $("srcSummary").textContent = "";
  $("startMsg").textContent = "";
  $("prog").classList.remove("hidden");
  $("start").classList.add("hidden");
  $("stop").classList.remove("hidden");
  ($("stop") as HTMLButtonElement).textContent = "■ Остановить";

  const threshold = parseFloat(($("thr") as HTMLInputElement).value);
  const reset = ($("reset") as HTMLInputElement).checked;

  let sources;
  try {
    $("srcName").textContent = "Получаю список источников…";
    sources = await buildSources(sel);
  } catch (e) {
    $("srcName").textContent = "ОШИБКА источников: " + (e as Error).message;
    finishRun();
    return;
  }

  for (let i = 0; i < sources.length; i++) {
    if (stopFlag) break;
    const s = sources[i];
    $("srcName").textContent = `Источник ${i + 1}/${sources.length}: ${s.playlistName}`;
    const deps: MigrationDeps = {
      getTracks: s.getTracks,
      search: searchSongs,
      createPlaylist: (t, d) => createPlaylist(t, d, "PRIVATE"),
      addItem: addPlaylistItem,
      loadState: () => loadMigState(s.key),
      saveState: (st) => saveMigState(s.key, st),
    };
    await runMigration(
      deps,
      { playlistName: s.playlistName, playlistDesc: "Импорт из Яндекс.Музыки", threshold, sleepMs: 400, reset },
      render,
      () => stopFlag,
    );
    if (lastProgress) {
      accMisses.push(...lastProgress.misses);
      summary.push(`✓ ${s.playlistName} — найдено ${lastProgress.matched}/${lastProgress.total}`);
      $("srcSummary").innerHTML = summary.map(esc).join("<br>");
    }
  }

  finishRun();
});

function finishRun() {
  $("stop").classList.add("hidden");
  $("start").classList.remove("hidden");
  ($("start") as HTMLButtonElement).textContent = "▶ Запустить снова";
  $("srcName").textContent = stopFlag ? "Остановлено." : "Готово.";
}

const PHASES: Record<string, string> = {
  idle: "ожидание", fetching: "выгрузка", creating: "создание плейлиста",
  matching: "перенос", done: "готово", stopped: "остановлено", error: "ошибка",
};

function render(p: Progress) {
  lastProgress = p;
  $("phase").textContent = PHASES[p.phase] ?? p.phase;
  $("sTotal").textContent = String(p.total);
  $("sProc").textContent = String(p.processed);
  $("sOk").textContent = String(p.matched);
  $("sMiss").textContent = String(p.missed);
  ($("fill") as HTMLElement).style.width = (p.total ? Math.round((p.processed / p.total) * 100) : 0) + "%";
  $("cur").textContent = p.current ? "Сейчас: " + p.current : "";

  const logEl = $("log");
  const atBottom = logEl.scrollTop + logEl.clientHeight >= logEl.scrollHeight - 20;
  logEl.innerHTML = p.log
    .map((l) => {
      let c = "";
      if (l.startsWith("OK")) c = "ok";
      else if (l.startsWith("MISS")) c = "miss";
      else if (l.includes("ОШИБКА") || l.includes("ошибка")) c = "err";
      return `<div class="${c}">${esc(l)}</div>`;
    })
    .join("");
  if (atBottom) logEl.scrollTop = logEl.scrollHeight;

  if (p.playlistId) {
    $("plLink").innerHTML =
      `<a href="https://music.youtube.com/playlist?list=${p.playlistId}" target="_blank">Открыть плейлист ↗</a>`;
  }
  const allMisses = [...accMisses, ...p.misses];
  if (allMisses.length) {
    $("missCard").classList.remove("hidden");
    ($("missBody") as HTMLElement).innerHTML = allMisses
      .slice(-400)
      .map((m) => `<tr><td>${esc(m.ya)}</td><td>${esc(m.reason)}</td></tr>`)
      .join("");
  }
}

function esc(s: string): string {
  return (s || "").replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]!));
}

refreshAuth();
chrome.storage.onChanged.addListener(() => refreshAuth());
