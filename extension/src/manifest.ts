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
  options_ui: { page: "src/ui/migrate.html", open_in_tab: true },
  content_scripts: [
    {
      matches: ["https://music.yandex.ru/*", "https://*.music.yandex.ru/*"],
      js: ["src/content/yandex-oauth.ts"],
      run_at: "document_start",
    },
  ],
});
