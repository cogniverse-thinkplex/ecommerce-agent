#!/usr/bin/env node

const baseUrl = (process.env.BASE_URL || "http://127.0.0.1:8000").replace(/\/$/, "");

let cookie = "";
async function get(path, options = {}) {
  const response = await fetch(`${baseUrl}${path}`, {
    ...options,
    headers: {...(options.headers || {}), ...(cookie ? {Cookie: cookie} : {})},
  });
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(`${path} returned HTTP ${response.status}: ${detail}`);
  }
  return response;
}

const login = await get("/api/v1/auth/login", {
  method: "POST",
  headers: {"Content-Type": "application/json"},
  body: JSON.stringify({
    email: process.env.SUPPORT_TEST_EMAIL || "ivan.santos3158@example.com",
    password: process.env.SUPPORT_TEST_PASSWORD || "DemoCustomer@123",
  }),
});
cookie = login.headers.get("set-cookie")?.split(";", 1)[0] || "";
if (!cookie) throw new Error("login did not issue an HttpOnly session cookie");

const html = await (await get("/support/")).text();
const css = await (await get("/support/styles.css")).text();
const app = await (await get("/support/app.js")).text();
const cards = await (await get("/support/cards.js")).text();
const feedbackHtml = await (await get("/support/feedback/")).text();
const accountHtml = await (await get("/account/")).text();

for (const expected of ["在线客服", 'aria-label="发送消息"', 'aria-live="polite"']) {
  if (!html.includes(expected)) throw new Error(`support HTML missing ${expected}`);
}
for (const forbidden of ["reward", "cost", "policy", "trace", "benchmark"]) {
  if (html.toLowerCase().includes(forbidden)) throw new Error(`support HTML exposes ${forbidden}`);
}
if (!css.includes("@media (max-width: 760px)")) throw new Error("mobile breakpoint missing");
if (!css.includes("minmax(0, 1fr)")) throw new Error("overflow-safe layout missing");
if (!html.includes('href="/account/"') || !html.includes('href="/support/feedback/"')) {
  throw new Error("account or issue-feedback navigation missing");
}
for (const removed of ['id="retail-auth-state"', 'id="conversation-feedback"', "有帮助", "没帮助"]) {
  if (html.includes(removed)) throw new Error(`obsolete support control still visible: ${removed}`);
}
if (!accountHtml.includes('id="profile-form"')) throw new Error("account editing page missing");
if (!feedbackHtml.includes('id="feedback-form"') || !feedbackHtml.includes('value="interface"')) {
  throw new Error("dedicated issue-feedback form missing");
}
if (!app.includes("accountIdentity.textContent")) throw new Error("customer name rendering missing");
if (!cards.includes("itemList") || !cards.includes("addressText")) {
  throw new Error("human-readable order card formatting missing");
}

const originalProfile = await (await get("/api/v1/auth/me")).json();
const profile = await (await get("/api/v1/auth/me", {
  method: "PATCH",
  headers: {"Content-Type": "application/json"},
  body: JSON.stringify({display_name: "界面验收用户"}),
})).json();
if (profile.display_name !== "界面验收用户") throw new Error("profile update did not persist");
await get("/api/v1/auth/me", {
  method: "PATCH",
  headers: {"Content-Type": "application/json"},
  body: JSON.stringify({display_name: originalProfile.display_name}),
});

const created = await (await get("/api/v1/support/conversations", {method: "POST"})).json();
const restored = await (await get(`/api/v1/support/conversations/${created.conversation_id}`)).json();
if (restored.conversation_id !== created.conversation_id) {
  throw new Error("created conversation could not be restored");
}

const question = "请   帮我查询这个订单的最新状态，并说明接下来可以办理哪些售后操作";
const turn = await (await get(`/api/v1/support/conversations/${created.conversation_id}/messages`, {
  method: "POST",
  headers: {"Content-Type": "application/json"},
  body: JSON.stringify({content: question, request_id: crypto.randomUUID()}),
})).json();
if (!Array.isArray(turn.blocks) || turn.blocks.length === 0) {
  throw new Error("support turn returned no customer-visible response");
}
const conversations = await (await get("/api/v1/support/conversations")).json();
const summarized = conversations.conversations.find((item) => item.conversation_id === created.conversation_id);
if (!summarized || summarized.title === "新会话" || summarized.title.length > 32) {
  throw new Error("first question did not produce a bounded conversation title");
}
if (summarized.message_count !== 1 || !summarized.last_question_at) {
  throw new Error("question count or last-question time is incorrect");
}

const group = await (await get("/api/v1/support/conversation-groups", {
  method: "POST", headers: {"Content-Type": "application/json"},
  body: JSON.stringify({name: "自动验收分组"}),
})).json();
const managed = await (await get(`/api/v1/support/conversations/${created.conversation_id}`, {
  method: "PATCH", headers: {"Content-Type": "application/json"},
  body: JSON.stringify({title: "自动验收会话", is_pinned: true, group_id: group.group_id}),
})).json();
if (managed.title !== "自动验收会话" || !managed.is_pinned || managed.group_id !== group.group_id) {
  throw new Error("conversation management fields did not persist");
}
await get(`/api/v1/support/conversation-groups/${group.group_id}`, {method: "DELETE"});
const ungrouped = await (await get(`/api/v1/support/conversations/${created.conversation_id}`)).json();
if (ungrouped.group_id !== null) throw new Error("deleting a group did not preserve and ungroup its conversations");

const emptyOne = await (await get("/api/v1/support/conversations", {method: "POST"})).json();
const emptyTwo = await (await get("/api/v1/support/conversations", {method: "POST"})).json();
const afterCleanup = await (await get("/api/v1/support/conversations")).json();
if (afterCleanup.conversations.some(item => item.conversation_id === emptyOne.conversation_id)) {
  throw new Error("creating a new conversation did not archive the prior empty conversation");
}
await get(`/api/v1/support/conversations/${emptyTwo.conversation_id}`, {method: "DELETE"});
if ((await fetch(`${baseUrl}/api/v1/support/conversations/${emptyTwo.conversation_id}`, {headers:{Cookie:cookie}})).status !== 404) {
  throw new Error("logical deletion did not hide the conversation");
}

const feedback = await (await get("/api/v1/support/feedback", {
  method: "POST",
  headers: {"Content-Type": "application/json"},
  body: JSON.stringify({
    category: "interface",
    comment: "自动验收提交的问题反馈。",
    conversation_id: created.conversation_id,
  }),
})).json();
if (feedback.rating !== "not_helpful" || feedback.category !== "interface") {
  throw new Error("issue feedback was not stored with compatibility fields");
}

console.log(`Support UI acceptance passed: ${created.conversation_id}`);
