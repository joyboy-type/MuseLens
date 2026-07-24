import assert from "node:assert/strict";
import { readFile, readdir } from "node:fs/promises";
import test from "node:test";

test("production build contains the MuseLens SPA", async () => {
  const html = await readFile(new URL("../dist/index.html", import.meta.url), "utf8");
  const assets = await readdir(new URL("../dist/assets", import.meta.url));

  assert.match(html, /<div id="root"><\/div>/);
  assert.match(html, /MuseLens/);
  assert.ok(assets.some((name) => name.endsWith(".js")));
  assert.ok(assets.some((name) => name.endsWith(".css")));

  const scripts = await Promise.all(
    assets
      .filter((name) => name.endsWith(".js"))
      .map((name) => readFile(new URL(`../dist/assets/${name}`, import.meta.url), "utf8")),
  );
  assert.match(scripts.join("\n"), /重置筛选/);
});
