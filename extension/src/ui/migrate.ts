import { ytIsLoggedIn } from "../auth/yt";
import { yandexIsLoggedIn } from "../auth/yandex";
import { searchSongs, createPlaylist, addPlaylistItem } from "../yt/api";
import { getLikedTracks } from "../yandex/api";
import { loadMigState, saveMigState } from "../storage/state";
import { runMigration, MigrationDeps, Progress } from "../engine/migrate";

const $ = (id: string) => document.getElementById(id)!;
const STATE_KEY = "state_likes";
let stopFlag = false;

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
  stopFlag = false;
  $("prog").classList.remove("hidden");
  $("start").classList.add("hidden");
  $("stop").classList.remove("hidden");
  ($("stop") as HTMLButtonElement).textContent = "■ Остановить";

  const deps: MigrationDeps = {
    getTracks: getLikedTracks,
    search: searchSongs,
    createPlaylist: (t, d) => createPlaylist(t, d, "PRIVATE"),
    addItem: addPlaylistItem,
    loadState: () => loadMigState(STATE_KEY),
    saveState: (s) => saveMigState(STATE_KEY, s),
  };

  await runMigration(
    deps,
    {
      playlistName: ($("plName") as HTMLInputElement).value.trim() || "Yandex Likes",
      playlistDesc: "Импорт лайков из Яндекс.Музыки",
      threshold: parseFloat(($("thr") as HTMLInputElement).value),
      sleepMs: 400,
      reset: ($("reset") as HTMLInputElement).checked,
    },
    render,
    () => stopFlag,
  );

  $("stop").classList.add("hidden");
  $("start").classList.remove("hidden");
  ($("start") as HTMLButtonElement).textContent = "▶ Запустить снова";
});

const PHASES: Record<string, string> = {
  idle: "ожидание", fetching: "выгрузка", creating: "создание плейлиста",
  matching: "перенос", done: "готово", stopped: "остановлено", error: "ошибка",
};

function render(p: Progress) {
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
  if (p.misses.length) {
    $("missCard").classList.remove("hidden");
    ($("missBody") as HTMLElement).innerHTML = p.misses
      .slice(-300)
      .map((m) => `<tr><td>${esc(m.ya)}</td><td>${esc(m.reason)}</td></tr>`)
      .join("");
  }
}

function esc(s: string): string {
  return (s || "").replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]!));
}

refreshAuth();
chrome.storage.onChanged.addListener(() => refreshAuth());
