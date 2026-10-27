import assert from "node:assert/strict";
import fs from "node:fs";

const html=fs.readFileSync("frontend/help/index.html","utf8");
const js=fs.readFileSync("frontend/help/help.js","utf8");
const css=fs.readFileSync("frontend/help/help.css","utf8");

assert.match(html,/购物政策|帮助中心/);
assert.match(html,/policy-search|search/);
assert.match(js,/\/api\/v1\/help\/search/);
assert.match(js,/assistant/);
assert.match(css,/@media/);
console.log("help UI validation passed");
