// SPDX-License-Identifier: LGPL-3.0-or-later
// Copyright (C) 2026 LiteZero

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { createRequire } = require("node:module");
const { spawn } = require("node:child_process");

const root = path.resolve(__dirname, "..");
const player = path.resolve(
  process.argv[2] || path.join(root, "../SPlayer-Next"),
);
const playerRequire = createRequire(path.join(player, "package.json"));
const packages = path.join(player, "node_modules/.pnpm");
const esbuildName = fs
  .readdirSync(packages)
  .find((name) => /^esbuild@/.test(name));
const esbuild = require(
  path.join(packages, esbuildName, "node_modules/esbuild"),
);
const build = path.join(root, "build/host-smoke");
fs.mkdirSync(build, { recursive: true });
esbuild.buildSync({
  entryPoints: [path.join(player, "electron/main/plugins/host.worker.ts")],
  bundle: true,
  platform: "node",
  format: "cjs",
  outfile: path.join(build, "worker.cjs"),
});
const main = `
const { app, net, utilityProcess } = require("electron");
const fs = require("node:fs");
const assert = require("node:assert/strict");
const { execFileSync } = require("node:child_process");
const report = { startedAt: new Date().toISOString(), checks: [], samples: [], requests: [], logs: [] };
app.setPath("userData", ${JSON.stringify(path.join(build, "user-data"))});
app.disableHardwareAcceleration();
const pluginId = "litezero.k20gt-lyrics";
let worker;
let snapshot = { position: 0, state: "paused", playing: false, speed: 1, lyricOffsetMs: 0, sendTimestamp: Date.now() };
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
const write = () => fs.writeFileSync(${JSON.stringify(path.join(root, "tests/host-smoke.json"))}, JSON.stringify(report, null, 2));
const announce = message => { console.log(message); write(); };
const sample = label => {
  const processes = app.getAppMetrics().map(item => ({ type: item.type, pid: item.pid, workingSetMB: Number((item.memory.workingSetSize / 1024).toFixed(2)) }));
  const bridge = execFileSync("tasklist.exe", ["/FI", "IMAGENAME eq SPlayerEC-Bridge.exe", "/FO", "CSV", "/NH"], { windowsHide: true }).toString();
  report.samples.push({ label, at: new Date().toISOString(), processes, bridgeTasklist: bridge });
  announce("MEMORY " + label + " " + JSON.stringify(processes));
};
const send = (event, data) => worker.postMessage({ kind: "event", pluginId, event, data });
const anchor = next => { snapshot = { ...snapshot, ...next, sendTimestamp: Date.now() }; };
const health = async () => { const response = await net.fetch("http://127.0.0.1:19620/health"); return response.json(); };
const expectText = async (text, before = -1) => {
  const end = Date.now() + 5000;
  while (Date.now() < end) {
    const state = await health();
    if (state.text === text && (text ? state.state === "connected" && state.writes > before : state.state === "waiting")) {
      report.checks.push({ text, state, at: new Date().toISOString() });
      write();
      return state;
    }
    await delay(100);
  }
  throw new Error("未显示预期文字：" + text + " " + JSON.stringify(await health()));
};
const lyric = (text, translation = "") => [{ startTime: 0, endTime: 10000, words: [{ word: text }], translatedLyric: translation }];
app.whenReady().then(async () => {
  await health();
  worker = utilityProcess.fork(${JSON.stringify(path.join(build, "worker.cjs"))}, [], { serviceName: "SPlayerEC plugin verification", stdio: "pipe" });
  worker.stdout.on("data", data => console.log(String(data)));
  worker.stderr.on("data", data => console.error(String(data)));
  let readyResolve;
  const ready = new Promise(resolve => { readyResolve = resolve; });
  let loadedResolve;
  const loaded = new Promise(resolve => { loadedResolve = resolve; });
  worker.on("message", async msg => {
    if (msg.kind === "hostReady") readyResolve();
    if (msg.kind === "ready") loadedResolve();
    if (msg.kind === "fatal") { report.error = msg.error; write(); app.exit(1); }
    if (msg.kind === "registered") report.registration = msg;
    if (msg.kind === "log") { report.logs.push(msg); write(); }
    if (msg.kind === "hostCall") {
      try {
        let data;
        if (msg.method === "player.getNowPlaying") data = { ...snapshot };
        else if (msg.method === "request") {
          const [url, options] = msg.args;
          assert.equal(url, "http://127.0.0.1:19620/v1/display");
          const response = await net.fetch(url, { method: options.method, headers: options.headers, body: options.body, credentials: "omit", signal: AbortSignal.timeout(options.timeout) });
          data = { status: response.status, headers: {}, body: await response.json() };
          report.requests.push({ text: JSON.parse(options.body).text, status: response.status, at: Date.now() });
        } else throw new Error("意外的宿主调用：" + msg.method);
        worker.postMessage({ kind: "hostResult", pluginId, callId: msg.callId, ok: true, data });
      } catch (error) {
        worker.postMessage({ kind: "hostResult", pluginId, callId: msg.callId, ok: false, error: { code: "SMOKE_ERROR", message: String(error) } });
      }
    }
  });
  await Promise.race([ready, delay(10000).then(() => { throw new Error("插件宿主启动超时"); })]);
  announce("开始 60 秒基线采样");
  await delay(60000);
  sample("host-empty-60s");
  worker.postMessage({ kind: "loadPlugin", pluginId, apiLevel: 4, locale: "zh-CN", appVersion: "1.2.0-beta.1", userSettings: {}, source: fs.readFileSync(${JSON.stringify(path.join(root, "plugin/k20gt-lyrics.js"))}, "utf8"), scriptInfo: { name: "K20 GT 音箱歌词", version: "1.0.0", author: "LiteZero", description: "", homepage: "" } });
  await Promise.race([loaded, delay(10000).then(() => { throw new Error("插件加载超时"); })]);
  assert.ok(report.registration.events.includes("lyricChange"));
  send("trackChange", { track: { id: "smoke", duration: 100000 } });
  send("lyricChange", { lines: lyric("SPlayerEC 歌词测试") });
  send("playStateChange", { state: "paused", position: 0 });
  let state = await expectText("SPlayerEC 歌词测试");
  const long = "中文分页测试".repeat(5);
  anchor({ position: 1000 });
  send("lyricChange", { lines: lyric(long, "翻译同步测试") });
  state = await expectText(long.slice(0, 17), state.writes);
  anchor({ position: 6000 });
  state = await expectText(long.slice(17), state.writes);
  worker.postMessage({ kind: "settingsUpdate", pluginId, settings: { language: "translation" } });
  state = await expectText("翻译同步测试", state.writes);
  send("lyricChange", { lines: [] });
  await expectText("");
  anchor({ position: 0 });
  send("lyricChange", { lines: lyric("后台歌词互联测试") });
  await expectText("后台歌词互联测试", state.writes);
  announce("实际设备写入已通过，开始 60 秒插件启用采样");
  await delay(60000);
  sample("plugin-enabled-60s");
  assert.equal(report.logs.filter(item => item.level === "warn" || item.level === "error").length, 0);
  worker.postMessage({ kind: "unloadPlugin", pluginId });
  await delay(9000);
  const released = await health();
  assert.equal(released.active, false);
  assert.equal(released.state, "waiting");
  assert.equal(released.text, "");
  report.released = released;
  announce("插件卸载后的自动清屏释放已通过，开始 60 秒释放后采样");
  await delay(60000);
  sample("plugin-unloaded-60s");
  worker.kill();
  report.complete = true;
  write();
  app.quit();
}).catch(error => { report.error = String(error.stack || error); write(); console.error(error); if(worker) worker.kill(); app.exit(1); });
`;
const entry = path.join(build, "main.cjs");
fs.writeFileSync(entry, main);
const electron = playerRequire("electron");
assert.ok(fs.existsSync(electron));
const environment = { ...process.env };
delete environment.ELECTRON_RUN_AS_NODE;
const child = spawn(electron, [entry], {
  cwd: root,
  windowsHide: true,
  stdio: "inherit",
  env: environment,
});
child.on("exit", (code) => process.exit(code ?? 1));
