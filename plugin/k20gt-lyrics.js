/**
 * SPDX-License-Identifier: LGPL-3.0-or-later
 * Copyright (C) 2026 LiteZero
 *
 * @name K20 GT 音箱歌词
 * @id litezero.k20gt-lyrics
 * @version 1.0.1
 * @description 通过本机 SPlayerEC 桥接程序显示歌词，无需修改播放器
 * @author LiteZero
 * @type control
 * @apiLevel 2
 * @grant network control
 */
(
  () => {
    "use strict";

    const endpoint = "http://127.0.0.1:19620/v1/display";
    const encoder = new TextEncoder();
    const hasSnapshot =
      splayer.apiLevel >= 4 &&
      typeof splayer.player.getNowPlaying === "function";
    let captions = [];
    let trackDuration = 0;
    let anchor = null;
    let legacyState = "paused";
    let legacyIndex = null;
    let revision = 0;
    let syncing = false;
    let syncAgain = false;
    let syncAt = 0;
    let sending = false;
    let pending = null;
    let delivered = null;
    let deliveredAt = 0;
    let retryAt = 0;
    let warned = false;
    let snapshotWarned = false;
    let enabled = true;
    let language = "original";

    splayer.register({
      events: ["trackChange", "lyricChange", "lineChange", "playStateChange"],
      controls: true,
      settings: [
        {
          key: "enabled",
          type: "switch",
          label: "音箱歌词同步",
          default: true,
        },
        {
          key: "language",
          type: "select",
          label: "显示语言",
          default: "original",
          options: [
            { label: "原文", value: "original" },
            { label: "翻译", value: "translation" },
            { label: "音译", value: "romanization" },
          ],
        },
      ],
    });
    enabled = splayer.getSetting("enabled") !== false;
    const savedLanguage = splayer.getSetting("language");
    language = ["original", "translation", "romanization"].includes(
      savedLanguage,
    )
      ? savedLanguage
      : "original";

    /**
     * 按 UTF-8 容量分页，保持 Unicode 字符完整
     * @param text - 一行歌词
     * @returns 每页不超过 52 字节的文本
     */
    function splitText(text) {
      const pages = [];
      let page = "";
      let length = 0;
      for (const char of text) {
        const size = encoder.encode(char).length;
        if (length + size > 52) {
          pages.push(page);
          page = "";
          length = 0;
        }
        page += char;
        length += size;
      }
      if (page) pages.push(page);
      return pages;
    }

    /**
     * 仅缓存当前曲目的轻量文字和时间，不保留逐字歌词对象
     * @param lines - 播放器推送的已解析歌词
     */
    function prepare(lines) {
      captions = lines.flatMap((line, sourceIndex) => {
        if (line.isBG) return [];
        const original = line.words.map((word) => word.word).join("");
        return [
          {
            sourceIndex,
            start: line.startTime,
            end: line.endTime,
            original,
            translation: line.translatedLyric || original,
            romanization: line.romanLyric || original,
            pages: [],
          },
        ];
      });
      for (let index = 0; index < captions.length - 1; index++) {
        captions[index].end = Math.min(
          captions[index].end,
          captions[index + 1].start,
        );
      }
      repaginate();
    }

    /** 根据当前语言重新分页，缺少译文时使用原文 */
    function repaginate() {
      for (const caption of captions) {
        caption.pages = splitText(caption[language].trim());
      }
    }

    /**
     * 使用快照或旧版行事件计算当前页，旧版按实测进度翻页
     * @param now - 当前墙钟毫秒
     * @returns 当前页或清屏用空字符串
     */
    function currentText(now) {
      if (
        !enabled ||
        !anchor ||
        ["idle", "loading", "stopped"].includes(anchor.state)
      )
        return "";
      const elapsed = anchor.playing
        ? Math.max(0, now - anchor.sendTimestamp) * anchor.speed
        : 0;
      const position = anchor.position + elapsed + anchor.lyricOffsetMs;
      const byIndex = !hasSnapshot && legacyIndex !== null;
      const target = byIndex ? legacyIndex : position;
      let low = 0;
      let high = captions.length;
      while (low < high) {
        const mid = (low + high) >>> 1;
        if (
          (byIndex ? captions[mid].sourceIndex : captions[mid].start) <= target
        )
          low = mid + 1;
        else high = mid;
      }
      const caption = captions[low - 1];
      const end = Math.min(caption?.end ?? 0, trackDuration || Infinity);
      if (!caption || !caption.pages.length) return "";
      if (
        position >= end &&
        (!byIndex || position < (captions[low]?.start ?? Infinity))
      )
        return "";
      const page = Math.max(
        0,
        Math.min(
          caption.pages.length - 1,
          Math.floor(
            ((position - caption.start) / Math.max(1, end - caption.start)) *
              caption.pages.length,
          ),
        ),
      );
      return caption.pages[page];
    }

    /** 串行发送短请求，最多保留一条在途和一条最新待发内容 */
    async function drain() {
      if (sending || Date.now() < retryAt) return;
      sending = true;
      try {
        while (pending !== null) {
          const text = pending;
          pending = null;
          const response = await splayer.request(endpoint, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ text }),
            responseType: "json",
            timeout: 1500,
          });
          if (response.status !== 200 || response.body?.ok !== true) {
            throw new Error(`桥接程序返回 ${response.status}`);
          }
          delivered = text;
          deliveredAt = Date.now();
          if (pending === text) pending = null;
          if (warned) splayer.log.info("SPlayerEC 桥接连接已恢复");
          warned = false;
        }
      } catch (error) {
        delivered = null;
        pending = null;
        retryAt = Date.now() + 3000;
        if (!warned)
          splayer.log.warn("无法连接 SPlayerEC，请启动桥接程序", String(error));
        warned = true;
      } finally {
        sending = false;
      }
    }

    /** 仅在页面变化或续期心跳时发送，停用后不再持续请求 */
    function tick() {
      const now = Date.now();
      if (!enabled && delivered === "" && pending === null) return;
      const text = currentText(now);
      if (pending !== null) pending = text;
      if (text !== delivered || (enabled && now - deliveredAt >= 2000)) {
        pending = text;
        void drain();
      }
    }

    /** 合并播放位置请求，旧版使用 API 2 进度接口并丢弃过期返回 */
    async function sync() {
      if (!enabled) return;
      if (syncing) {
        syncAgain = true;
        return;
      }
      syncing = true;
      const started = revision;
      try {
        const next = hasSnapshot
          ? await splayer.player.getNowPlaying()
          : {
              position: await splayer.player.getPosition(),
              state: legacyState,
              playing: false,
              speed: 1,
              lyricOffsetMs: 0,
              sendTimestamp: Date.now(),
            };
        if (started === revision) anchor = next;
        snapshotWarned = false;
      } catch (error) {
        anchor = null;
        if (!snapshotWarned)
          splayer.log.warn(
            "读取播放进度失败，请检查 control 权限",
            String(error),
          );
        snapshotWarned = true;
      } finally {
        syncing = false;
        syncAt = Date.now();
        tick();
        if (syncAgain) {
          syncAgain = false;
          void sync();
        }
      }
    }

    splayer.player.on("trackChange", ({ track }) => {
      revision++;
      captions = [];
      anchor = null;
      legacyState = "paused";
      legacyIndex = null;
      trackDuration = track?.duration || 0;
      tick();
      void sync();
    });
    splayer.player.on("lyricChange", ({ lines }) => {
      legacyIndex = null;
      prepare(lines);
      void sync();
      tick();
    });
    splayer.player.on("lineChange", ({ index, position }) => {
      if (!hasSnapshot) {
        revision++;
        legacyIndex = index;
        if (anchor) anchor = { ...anchor, position };
        tick();
      }
      void sync();
    });
    splayer.player.on("playStateChange", ({ state, position }) => {
      if (!hasSnapshot) {
        revision++;
        legacyState = state;
        anchor = {
          position,
          state,
          playing: false,
          speed: 1,
          lyricOffsetMs: 0,
          sendTimestamp: Date.now(),
        };
        tick();
      }
      void sync();
    });
    splayer.onSettingChange("enabled", (value) => {
      enabled = value !== false;
      anchor = null;
      tick();
      if (enabled) void sync();
    });
    splayer.onSettingChange("language", (value) => {
      language = ["original", "translation", "romanization"].includes(value)
        ? value
        : "original";
      repaginate();
      tick();
    });
    setInterval(() => {
      if (enabled && Date.now() - syncAt >= (hasSnapshot ? 500 : 200))
        void sync();
      tick();
    }, 100);
    void sync();
  }
)();
