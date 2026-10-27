#!/usr/bin/env node

const baseUrl = (process.env.BASE_URL || "http://127.0.0.1:8020").replace(/\/$/, "");

async function read(path) {
  const response = await fetch(`${baseUrl}${path}`);
  if (!response.ok) throw new Error(`${path} returned HTTP ${response.status}`);
  return {response, body: await response.text()};
}

for (const [path, heading] of [["/login/", "欢迎回来"], ["/register/", "创建账户"]]) {
  const {body} = await read(path);
  if (!body.includes(heading)) throw new Error(`${path} missing ${heading}`);
  if (!body.includes("data-password-toggle")) throw new Error(`${path} missing password toggle`);
  if (!body.includes("?v=20261023-ac")) throw new Error(`${path} missing asset cache version`);
  for (const forbidden of ["普通用户进入客服中心", "工程观测控制台", "注册普通用户"]) {
    if (body.includes(forbidden)) throw new Error(`${path} exposes internal copy: ${forbidden}`);
  }
}

const {body: css} = await read("/auth/auth.css?v=20261023-ac");
for (const expected of ["auth-fulfillment.webp", "@media (max-width: 760px)", ".password-toggle", ":focus-visible"]) {
  if (!css.includes(expected)) throw new Error(`auth CSS missing ${expected}`);
}

const image = await fetch(`${baseUrl}/auth/auth-fulfillment.webp`);
if (!image.ok || !image.headers.get("content-type")?.includes("image/webp")) {
  throw new Error("local fulfillment visual is unavailable");
}

console.log("Authentication UI acceptance passed");
