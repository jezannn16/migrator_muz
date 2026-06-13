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
