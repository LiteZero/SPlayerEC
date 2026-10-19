// SPDX-License-Identifier: LGPL-3.0-or-later
// Copyright (C) 2026 LiteZero

const { app, utilityProcess, net } = require("electron");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const http = require("node:http");
const path = require("node:path");

const build = process.argv[2];
const root = path.resolve(__dirname, "..");
const fixture = JSON.parse(
  fs.readFileSync(path.join(build, "fixture.json"), "utf8"),
);
const report = {
  installedVersion: fixture.installedVersion,
  apiLevel: 3,
  manifest: fixture.manifest,
  originalSourceSha256: fixture.originalSourceSha256,
  workerSha256: fixture.workerSha256,
  bridge: "isolated HTTP fixture on 127.0.0.1:19621",
  checks: [],
  logs: [],
  samples: [],
  methods: {},
};
app.setPath("userData", path.join(build, "user-data"));
app.disableHardwareAcceleration();
let worker;
let server;
let position = 0;
let state = "paused";
let received = "";
let requestCount = 0;

/**
 * 等待跨进程状态传播
 * @param ms - 等待毫秒数
 * @returns 到时完成的 Promise
 */
const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
/** 保存验证记录 */
const save = () =>
  fs.writeFileSync(
    path.join(root, "tests/legacy-host-smoke.json"),
    JSON.stringify(report, null, 2),
  );
/**
 * 采集隔离宿主工作集
 * @param label - 采样阶段名称
 */
const sample = (label) => {
  report.samples.push({
    label,
    at: new Date().toISOString(),
    processes: app.getAppMetrics().map((item) => ({
      type: item.type,
      workingSetMB: Number((item.memory.workingSetSize / 1024).toFixed(2)),
    })),
  });
  save();
  console.log(label);
};
/**
 * 向实际 API 3 沙箱推送播放事件
 * @param name - 播放事件名称
 * @param data - 宿主事件数据
 */
const event = (name, data) =>
  worker.postMessage({
    kind: "event",
    pluginId: fixture.manifest.id,
    event: name,
    data,
  });
/**
 * 等待实际宿主通过 HTTP 发出预期页面
 * @param text - 预期显示的文字
 */
const expectText = async (text) => {
  const end = Date.now() + 5000;
  while (Date.now() < end) {
    if (received === text) {
      report.checks.push({ text, at: new Date().toISOString() });
      save();
      return;
    }
    await delay(50);
  }
  throw new Error("预期：" + text + "，实际：" + received);
};
/**
 * 创建已解析歌词行
 * @param word - 原文歌词
 * @param translatedLyric - 翻译歌词
 * @returns 宿主使用的歌词行数组
 */
const lyric = (word, translatedLyric = "") => [
  { startTime: 0, endTime: 10000, words: [{ word }], translatedLyric },
];

app
  .whenReady()
  .then(async () => {
    server = http.createServer((request, response) => {
      let body = "";
      request.on("data", (chunk) => {
        body += chunk;
      });
      request.on("end", () => {
        try {
          assert.equal(request.url, "/v1/display");
          assert.equal(request.method, "POST");
          const payload = JSON.parse(body);
          assert.equal(typeof payload.text, "string");
          assert.ok(Buffer.byteLength(payload.text) <= 52);
          received = payload.text;
          requestCount++;
          response.writeHead(200, { "Content-Type": "application/json" });
          response.end('{"ok":true}');
        } catch (error) {
          report.httpError = String(error);
          response.writeHead(400);
          response.end("{}");
        }
      });
    });
    await new Promise((resolve, reject) => {
      server.once("error", reject);
      server.listen(19621, "127.0.0.1", resolve);
    });
    worker = utilityProcess.fork(path.join(build, "worker.mjs"), [], {
      stdio: "pipe",
      serviceName: "API 3 compatibility verification",
    });
    worker.stdout.on("data", (data) => console.log(String(data)));
    worker.stderr.on("data", (data) => console.error(String(data)));
    let hostReady;
    let pluginReady;
    const ready = new Promise((resolve) => {
      hostReady = resolve;
    });
    const loaded = new Promise((resolve) => {
      pluginReady = resolve;
    });
    worker.on("message", async (message) => {
      if (message.kind === "hostReady") hostReady();
      if (message.kind === "ready") pluginReady();
      if (message.kind === "registered") report.registration = message;
      if (message.kind === "log") report.logs.push(message);
      if (message.kind === "fatal") {
        report.error = message.error;
        save();
        app.exit(1);
      }
      if (message.kind !== "hostCall") return;
      report.methods[message.method] =
        (report.methods[message.method] || 0) + 1;
      try {
        let data;
        if (message.method === "player.getPosition") data = position;
        else if (message.method === "request") {
          const [url, options] = message.args;
          assert.equal(url, "http://127.0.0.1:19621/v1/display");
          const response = await net.fetch(url, {
            method: options.method,
            headers: options.headers,
            body: options.body,
            signal: AbortSignal.timeout(options.timeout),
            credentials: "omit",
          });
          data = {
            status: response.status,
            headers: {},
            body: await response.json(),
          };
        } else throw new Error("旧版不支持的调用：" + message.method);
        worker.postMessage({
          kind: "hostResult",
          pluginId: fixture.manifest.id,
          callId: message.callId,
          ok: true,
          data,
        });
      } catch (error) {
        report.hostError = String(error);
        worker.postMessage({
          kind: "hostResult",
          pluginId: fixture.manifest.id,
          callId: message.callId,
          ok: false,
          error: { code: "SMOKE_ERROR", message: String(error) },
        });
      }
    });
    await Promise.race([
      ready,
      delay(10000).then(() => {
        throw new Error("API 3 宿主启动超时");
      }),
    ]);
    console.log("安装版 API 3 宿主已启动，开始 60 秒基线采样");
    await delay(60000);
    sample("empty-host-60s");
    worker.postMessage({
      kind: "loadPlugin",
      pluginId: fixture.manifest.id,
      apiLevel: 3,
      locale: "zh-CN",
      appVersion: fixture.installedVersion,
      userSettings: {},
      source: fixture.source,
      scriptInfo: {
        name: fixture.manifest.name,
        version: fixture.manifest.version,
        description: "",
        author: "LiteZero",
        homepage: "",
      },
    });
    await Promise.race([
      loaded,
      delay(10000).then(() => {
        throw new Error("API 3 插件加载超时");
      }),
    ]);
    assert.equal(report.registration.controls, true);
    event("trackChange", { track: { duration: 100000 } });
    event("lyricChange", { lines: lyric("API 3 歌词兼容测试") });
    event("playStateChange", { state, position });
    event("lineChange", { index: 0, position });
    await expectText("API 3 歌词兼容测试");
    const long = "中文分页测试".repeat(5);
    event("lyricChange", { lines: lyric(long, "旧版翻译测试") });
    event("lineChange", { index: 0, position });
    await expectText(long.slice(0, 17));
    position = 6000;
    await expectText(long.slice(17));
    worker.postMessage({
      kind: "settingsUpdate",
      pluginId: fixture.manifest.id,
      settings: { language: "translation" },
    });
    await expectText("旧版翻译测试");
    state = "stopped";
    event("playStateChange", { state, position });
    await expectText("");
    position = 0;
    state = "playing";
    event("playStateChange", { state, position });
    await expectText("旧版翻译测试");
    worker.postMessage({
      kind: "settingsUpdate",
      pluginId: fixture.manifest.id,
      settings: { enabled: false },
    });
    await expectText("");
    await delay(1000);
    const disabledCount = requestCount;
    await delay(2500);
    assert.equal(requestCount, disabledCount);
    worker.postMessage({
      kind: "settingsUpdate",
      pluginId: fixture.manifest.id,
      settings: { enabled: true },
    });
    await expectText("旧版翻译测试");
    console.log(
      "API 3 分页、暂停跳转、翻译、停止及停用已通过，开始 60 秒启用采样",
    );
    await delay(60000);
    sample("plugin-enabled-60s");
    assert.ok(report.methods["player.getPosition"] > 0);
    assert.equal(report.methods["player.getNowPlaying"], undefined);
    assert.equal(report.hostError, undefined);
    assert.equal(report.httpError, undefined);
    assert.equal(
      report.logs.filter(
        (item) => item.level === "warn" || item.level === "error",
      ).length,
      0,
    );
    worker.postMessage({ kind: "unloadPlugin", pluginId: fixture.manifest.id });
    await delay(1000);
    const unloadedCount = requestCount;
    await delay(2500);
    assert.equal(requestCount, unloadedCount);
    sample("plugin-unloaded");
    report.complete = true;
    save();
    worker.kill();
    server.close();
    app.quit();
  })
  .catch((error) => {
    report.error = String(error.stack || error);
    save();
    console.error(error);
    if (worker) worker.kill();
    if (server) server.close();
    app.exit(1);
  });
