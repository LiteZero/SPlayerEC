// SPDX-License-Identifier: LGPL-3.0-or-later
// Copyright (C) 2026 LiteZero

const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const source = fs.readFileSync(
  path.join(__dirname, "../plugin/k20gt-lyrics.js"),
  "utf8",
);

/**
 * 运行与宿主相同的插件脚本，使用可控时间和异步接口
 * @param options - 模拟 API 级别、设置和异步响应
 * @returns 事件、时钟与请求断言入口
 */
function harness(options = {}) {
  let now = 100000;
  let snapshot = {
    position: 0,
    state: "playing",
    playing: true,
    speed: 1,
    lyricOffsetMs: 0,
    sendTimestamp: now,
  };
  const events = {};
  const changes = {};
  const timers = [];
  const sent = [];
  const warnings = [];
  let positionReads = 0;
  let snapshotReads = 0;
  const settings = { language: "original", enabled: true, ...options.settings };
  class Clock extends Date {
    /** 返回测试控制的毫秒时间 */
    static now() {
      return now;
    }
  }
  const api = {
    apiLevel: options.apiLevel ?? 4,
    register: (data) => {
      api.registration = data;
    },
    getSetting: (key) => settings[key],
    onSettingChange: (key, handler) => {
      changes[key] = handler;
    },
    log: { warn: (...args) => warnings.push(args), info: () => {} },
    player: {
      on: (kind, handler) => {
        events[kind] = handler;
      },
      getPosition: async () => {
        positionReads++;
        return options.position
          ? options.position()
          : snapshot.position +
              (snapshot.playing
                ? (now - snapshot.sendTimestamp) * snapshot.speed
                : 0);
      },
    },
    request: async (_url, request) => {
      const text = JSON.parse(request.body).text;
      sent.push(text);
      if (options.request) return options.request(text);
      return { status: 200, body: { ok: true } };
    },
  };
  if (api.apiLevel >= 4) {
    api.player.getNowPlaying = async () => {
      snapshotReads++;
      return options.snapshot ? options.snapshot() : { ...snapshot };
    };
  }
  vm.runInNewContext(source, {
    splayer: api,
    TextEncoder,
    Date: Clock,
    setInterval: (fn) => timers.push(fn),
  });
  return {
    sent,
    warnings,
    api,
    reads: () => ({ position: positionReads, snapshot: snapshotReads }),
    flush: () => new Promise((resolve) => setImmediate(resolve)),
    event: (name, data) => events[name](data),
    setting: (key, value) => changes[key](value),
    snapshot: (next) => {
      snapshot = { ...snapshot, sendTimestamp: now, ...next };
    },
    step: (ms) => {
      now += ms;
      timers.forEach((fn) => fn());
    },
  };
}

/** 创建包含可选翻译和背景人声的最小歌词行 */
function line(text, start = 0, end = 10000, extra = {}) {
  return { startTime: start, endTime: end, words: [{ word: text }], ...extra };
}

/**
 * 等待启动清屏完成，再推送当前歌曲和歌词
 * @param h - 模拟宿主
 * @param lines - 当前曲目的歌词行
 */
async function prime(h, lines) {
  await h.flush();
  h.event("trackChange", { track: { id: "track", duration: 100000 } });
  h.event("lyricChange", { lines });
  if (h.api.apiLevel < 4) {
    h.event("playStateChange", { state: "playing", position: 0 });
    h.event("lineChange", { index: 0, position: 0 });
  }
  await h.flush();
}

test("中文与 emoji 分页不截断 UTF-8，时间推进后显示下一页", async () => {
  const h = harness();
  const text = "中文🎵".repeat(8);
  await prime(h, [line(text)]);
  const first = h.sent.at(-1);
  assert.ok(Buffer.byteLength(first) <= 52);
  assert.ok(!first.includes("\ufffd"));
  h.step(5500);
  await h.flush();
  const second = h.sent.at(-1);
  assert.equal(first + second, text);
});

test("声明旧版要求的控制插件类型和最低 API 2", () => {
  assert.match(source, /@apiLevel\s+2\b/);
  assert.match(source, /@type\s+control\b/);
  assert.match(source, /@grant\s+network control\b/);
});

for (const apiLevel of [2, 3]) {
  test(`API ${apiLevel} 不提供快照接口时仍能接收歌词并分页`, async () => {
    const h = harness({ apiLevel });
    assert.equal(h.api.player.getNowPlaying, undefined);
    await prime(h, [line("a".repeat(52) + "b".repeat(52))]);
    assert.equal(h.api.registration.controls, true);
    assert.equal(h.sent.at(-1), "a".repeat(52));
    h.step(5500);
    await h.flush();
    assert.equal(h.sent.at(-1), "b".repeat(52));
    assert.equal(h.reads().snapshot, 0);
    assert.ok(h.reads().position > 0);
    assert.equal(h.warnings.length, 0);
  });
}

test("API 3 按实测进度支持暂停、同一行跳转和倍速", async () => {
  const h = harness({ apiLevel: 3 });
  await prime(h, [line("a".repeat(52) + "b".repeat(52))]);
  h.snapshot({ position: 1000, playing: false, state: "paused" });
  h.event("playStateChange", { state: "paused", position: 1000 });
  await h.flush();
  h.step(2000);
  await h.flush();
  assert.equal(h.sent.at(-1), "a".repeat(52));
  h.snapshot({ position: 6000 });
  h.step(200);
  await h.flush();
  assert.equal(h.sent.at(-1), "b".repeat(52));
  h.snapshot({ position: 0, speed: 2, playing: true });
  h.event("playStateChange", { state: "playing", position: 0 });
  await h.flush();
  h.step(2600);
  await h.flush();
  assert.equal(h.sent.at(-1), "b".repeat(52));
  h.event("playStateChange", { state: "stopped", position: 5200 });
  await h.flush();
  assert.equal(h.sent.at(-1), "");
});

test("API 3 尊重当前行索引并保持背景人声索引对应", async () => {
  const h = harness({ apiLevel: 3 });
  await prime(h, [
    line("第一句", 0, 1000),
    line("背景", 500, 1000, { isBG: true }),
    line("提前显示", 5000, 10000),
  ]);
  h.snapshot({ position: 1000, playing: false });
  h.event("playStateChange", { state: "paused", position: 1000 });
  h.event("lineChange", { index: 2, position: 1000 });
  await h.flush();
  assert.equal(h.sent.at(-1), "提前显示");
  h.event("lineChange", { index: -1, position: 1000 });
  await h.flush();
  assert.equal(h.sent.at(-1), "");
});

test("翻译、音译、缺失回退和背景人声过滤", async () => {
  const h = harness();
  await prime(h, [
    line("原文", 0, 10000, { translatedLyric: "翻译", romanLyric: "roma" }),
    line("背景", 100, 9000, { isBG: true }),
  ]);
  assert.equal(h.sent.at(-1), "原文");
  h.setting("language", "translation");
  await h.flush();
  assert.equal(h.sent.at(-1), "翻译");
  h.setting("language", "romanization");
  await h.flush();
  assert.equal(h.sent.at(-1), "roma");
  h.event("lyricChange", { lines: [line("回退")] });
  await h.flush();
  assert.equal(h.sent.at(-1), "回退");
});

test("暂停保持当前页，同一行内 seek、偏移和倍速被快照纠正", async () => {
  const h = harness();
  await prime(h, [line("a".repeat(52) + "b".repeat(52))]);
  h.snapshot({ position: 1000, playing: false, state: "paused" });
  h.event("playStateChange", {});
  await h.flush();
  h.step(2000);
  await h.flush();
  assert.equal(h.sent.at(-1), "a".repeat(52));
  h.snapshot({ position: 6000 });
  h.step(500);
  await h.flush();
  assert.equal(h.sent.at(-1), "b".repeat(52));
  h.snapshot({ position: 1000, lyricOffsetMs: 5000 });
  h.step(500);
  await h.flush();
  assert.equal(h.sent.at(-1), "b".repeat(52));
  h.snapshot({
    position: 0,
    lyricOffsetMs: 0,
    playing: true,
    state: "playing",
    speed: 2,
  });
  h.event("playStateChange", {});
  await h.flush();
  h.step(2600);
  await h.flush();
  assert.equal(h.sent.at(-1), "b".repeat(52));
});

test("间奏、停止、无歌词和插件设置停用清屏", async () => {
  const h = harness();
  await prime(h, [line("歌词", 0, 1000), line("下一句", 5000, 8000)]);
  h.step(2000);
  await h.flush();
  assert.equal(h.sent.at(-1), "");
  h.snapshot({ position: 6000 });
  h.step(500);
  await h.flush();
  assert.equal(h.sent.at(-1), "下一句");
  h.setting("enabled", false);
  await h.flush();
  assert.equal(h.sent.at(-1), "");
  const count = h.sent.length;
  h.step(20000);
  await h.flush();
  assert.equal(h.sent.length, count);
  h.setting("enabled", true);
  h.snapshot({ state: "stopped", playing: false });
  h.event("playStateChange", {});
  await h.flush();
  assert.equal(h.sent.at(-1), "");
  h.event("lyricChange", { lines: [] });
  await h.flush();
  assert.equal(h.sent.at(-1), "");
});

test("相同文字只发送必要心跳", async () => {
  const h = harness();
  await prime(h, [line("不变")]);
  const count = h.sent.length;
  h.step(100);
  await h.flush();
  h.step(100);
  await h.flush();
  assert.equal(h.sent.length, count);
  h.step(2000);
  await h.flush();
  assert.equal(h.sent.length, count + 1);
});

test("慢请求最多保留一条在途和最新一条待发", async () => {
  let resolve;
  let block = false;
  const h = harness({
    request: async () => {
      if (block)
        await new Promise((done) => {
          resolve = done;
        });
      return { status: 200, body: { ok: true } };
    },
  });
  await prime(h, [line("第一句")]);
  block = true;
  h.event("lyricChange", { lines: [line("正在发送")] });
  await h.flush();
  h.event("lyricChange", { lines: [line("应被丢弃")] });
  h.event("lyricChange", { lines: [line("最新句")] });
  await h.flush();
  assert.equal(h.sent.at(-1), "正在发送");
  block = false;
  resolve();
  await h.flush();
  assert.equal(h.sent.at(-1), "最新句");
  assert.ok(!h.sent.includes("应被丢弃"));
});

test("桥接故障限制重试频率，恢复后只发送当前内容", async () => {
  let offline = true;
  const h = harness({
    request: async () => {
      if (offline) throw new Error("offline");
      return { status: 200, body: { ok: true } };
    },
  });
  await prime(h, [line("恢复后显示")]);
  const count = h.sent.length;
  h.step(1000);
  await h.flush();
  assert.equal(h.sent.length, count);
  assert.equal(h.warnings.length, 1);
  offline = false;
  h.step(2100);
  await h.flush();
  assert.equal(h.sent.at(-1), "恢复后显示");
});

test("切歌后丢弃旧快照，防止新歌词套用上一首进度", async () => {
  let deliver;
  let calls = 0;
  const h = harness({
    snapshot: () => {
      calls++;
      if (calls === 1)
        return new Promise((resolve) => {
          deliver = resolve;
        });
      return Promise.resolve({
        position: 0,
        playing: false,
        state: "paused",
        speed: 1,
        lyricOffsetMs: 0,
        sendTimestamp: 100000,
      });
    },
  });
  h.event("trackChange", { track: { duration: 10000 } });
  h.event("lyricChange", { lines: [line("新歌", 0, 1000)] });
  deliver({
    position: 9000,
    playing: false,
    state: "paused",
    speed: 1,
    lyricOffsetMs: 0,
    sendTimestamp: 100000,
  });
  await h.flush();
  assert.equal(h.sent.at(-1), "新歌");
});
