// SPDX-License-Identifier: LGPL-3.0-or-later
// Copyright (C) 2026 LiteZero

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const crypto = require("node:crypto");
const { createRequire } = require("node:module");
const { spawn } = require("node:child_process");

const root = path.resolve(__dirname, "..");
const playerRoot = path.resolve(root, "../SPlayer-Next");
const playerRequire = createRequire(path.join(playerRoot, "package.json"));
const packages = path.join(playerRoot, "node_modules/.pnpm");
const asarName = fs
  .readdirSync(packages)
  .find((name) => name.startsWith("@electron+asar@"));
const asar = require(
  path.join(packages, asarName, "node_modules/@electron/asar"),
);
const installed = process.argv[2] || "D:/Program Files/SPlayer-Next";
const archive = path.join(installed, "resources/app.asar");
const build = path.join(root, "build/legacy-host-smoke");
fs.mkdirSync(build, { recursive: true });
const mainSource = asar
  .extractFile(archive, path.join("out", "main", "index.js"))
  .toString();
const workerSource = asar.extractFile(
  archive,
  path.join("out", "main", "host.worker.js"),
);
const installedPackage = JSON.parse(
  asar.extractFile(archive, "package.json").toString(),
);
const apiLevel = Number(/const HOST_API_LEVEL = (\d+)/.exec(mainSource)[1]);
assert.equal(apiLevel, 3);
const parserStart = mainSource.indexOf("const PLUGIN_TYPES =");
const parserEnd = mainSource.indexOf("const fetchScript =", parserStart);
assert.ok(parserStart >= 0 && parserEnd > parserStart);
const context = {
  Buffer,
  path,
  crypto$1: crypto,
  zlib__default: require("node:zlib"),
  HOST_API_LEVEL: apiLevel,
  PluginErrorCodes: { API_LEVEL_MISMATCH: "API_LEVEL_MISMATCH" },
};
vm.runInNewContext(
  mainSource.slice(parserStart, parserEnd) + "\nglobalThis.parse = loadScript;",
  context,
);
const source = fs.readFileSync(
  path.join(root, "plugin/k20gt-lyrics.js"),
  "utf8",
);
const parsed = context.parse(source, false);
assert.equal(parsed.manifest.type, "control");
assert.equal(parsed.manifest.apiLevel, 2);
assert.ok(parsed.manifest.grant.includes("control"));
assert.ok(parsed.manifest.grant.includes("network"));
const workerPath = path.join(build, "worker.mjs");
fs.writeFileSync(workerPath, workerSource);
fs.writeFileSync(
  path.join(build, "fixture.json"),
  JSON.stringify({
    manifest: parsed.manifest,
    source: source.replace(
      "http://127.0.0.1:19620/v1/display",
      "http://127.0.0.1:19621/v1/display",
    ),
    originalSourceSha256: crypto
      .createHash("sha256")
      .update(source)
      .digest("hex"),
    installedVersion: installedPackage.version,
    workerSha256: crypto
      .createHash("sha256")
      .update(workerSource)
      .digest("hex"),
  }),
);
const environment = { ...process.env };
delete environment.ELECTRON_RUN_AS_NODE;
const child = spawn(
  playerRequire("electron"),
  [path.join(__dirname, "legacy-host-main.cjs"), build],
  {
    cwd: root,
    windowsHide: true,
    stdio: "inherit",
    env: environment,
  },
);
child.on("exit", (code) => process.exit(code ?? 1));
