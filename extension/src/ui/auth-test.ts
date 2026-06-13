import { searchSongs } from "../yt/api";
import { ytIsLoggedIn } from "../auth/yt";
import { getLikesCount, getUid } from "../yandex/api";
import { yandexIsLoggedIn } from "../auth/yandex";

const out = document.getElementById("out")!;
const log = (x: unknown) =>
  (out.textContent += (typeof x === "string" ? x : JSON.stringify(x, null, 2)) + "\n");

document.getElementById("ytBtn")!.addEventListener("click", async () => {
  try {
    log("YT logged in: " + (await ytIsLoggedIn()));
    const res = await searchSongs("kino gruppa krovi");
    log(`YT search -> ${res.length} songs`);
    log(res.slice(0, 3));
  } catch (e) {
    log("YT ERROR: " + (e as Error).message);
  }
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
  } catch (e) {
    log("Yandex ERROR: " + (e as Error).message);
  }
});
