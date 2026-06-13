import { parseYandexToken } from "../auth/yandex";

// Runs on music.yandex.ru pages (document_start). If the URL fragment carries an
// OAuth token (redirect from oauth.yandex.ru), forward it to the background worker.
const token = parseYandexToken(location.hash);
if (token) {
  chrome.runtime.sendMessage({ type: "YANDEX_TOKEN", token });
}
