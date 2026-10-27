#!/usr/bin/env node

const baseUrl = (process.env.BASE_URL || "http://127.0.0.1:8000").replace(/\/$/, "");
let cookie = "";

async function request(path, options = {}) {
  const response = await fetch(`${baseUrl}${path}`, {
    ...options,
    headers: {...(options.headers || {}), ...(cookie ? {Cookie: cookie} : {})},
  });
  if (!response.ok) throw new Error(`${path} returned ${response.status}: ${await response.text()}`);
  return response;
}

const login = await request("/api/v1/auth/login", {
  method: "POST",
  headers: {"Content-Type": "application/json"},
  body: JSON.stringify({
    email: process.env.SUPPORT_TEST_EMAIL || "ivan.santos3158@example.com",
    password: process.env.SUPPORT_TEST_PASSWORD || "DemoCustomer@123",
  }),
});
cookie = login.headers.get("set-cookie")?.split(";", 1)[0] || "";
if (!cookie) throw new Error("login did not issue a cookie");

const conversation = await (await request("/api/v1/support/conversations", {method:"POST"})).json();
const stream = await request(`/api/v1/support/conversations/${conversation.conversation_id}/messages/stream`, {
  method: "POST",
  headers: {"Content-Type":"application/json", "Accept":"text/event-stream"},
  body: JSON.stringify({content:"帮我查询全部订单", request_id:crypto.randomUUID()}),
});
const text = await stream.text();
const eventNames = [...text.matchAll(/^event: (.+)$/gm)].map(match => match[1]);
if (eventNames[0] !== "accepted") throw new Error("stream did not begin with accepted");
if (!eventNames.includes("progress")) throw new Error("stream returned no progress event");
if (!eventNames.includes("block")) throw new Error("stream returned no customer block");
if (eventNames.at(-1) !== "completed") throw new Error("stream did not complete");
if (text.indexOf("event: block") > text.indexOf("event: completed")) throw new Error("blocks were not emitted before completion");
for (const forbidden of ["chain-of-thought", "AVAILABLE_TOOLS", "POLICY:", "rationale"]) {
  if (text.includes(forbidden)) throw new Error(`stream exposed internal field: ${forbidden}`);
}

const handoff = await (await request(`/api/v1/support/conversations/${conversation.conversation_id}/handoff`, {
  method:"POST",
  headers:{"Content-Type":"application/json"},
  body:JSON.stringify({reason:"customer_requested", message:"自动验收人工接管。"}),
})).json();
if (handoff.status !== "open") throw new Error("handoff was not opened");
const restored = await (await request(`/api/v1/support/conversations/${conversation.conversation_id}/handoff`)).json();
if (restored.ticket_id !== handoff.ticket_id) throw new Error("handoff did not persist");

console.log(`Streaming and handoff acceptance passed: ${conversation.conversation_id} / ${handoff.ticket_id}`);
