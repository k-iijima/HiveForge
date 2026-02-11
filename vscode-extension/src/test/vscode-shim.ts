/**
 * vscode モジュールのテストシム
 *
 * VS Code拡張テスト実行時に `require('vscode')` を
 * vscode-mock.ts のモックに差し替える。
 * mocha --require out/test/vscode-shim.js で使用する。
 */

import * as vscodeMock from "./vscode-mock";

// 'vscode' というモジュール名でキャッシュに直接登録
// Node.js のモジュールキャッシュに偽のエントリを作成する
const fakeModulePath = "vscode";
const fakeModule = {
    id: fakeModulePath,
    filename: fakeModulePath,
    loaded: true,
    exports: vscodeMock,
    children: [],
    paths: [],
    path: "",
    parent: null,
    require: require,
} as unknown as NodeModule;

require.cache[fakeModulePath] = fakeModule;

// また、resolve後のパスでもキャッシュに入れる（Node.jsのバージョン互換性）
try {
    const resolvedPath = require.resolve("vscode");
    require.cache[resolvedPath] = fakeModule;
} catch {
    // vscodeモジュールがresolveできない場合は無視
}
