#!/usr/bin/env node

const baseUrl = (process.env.BASE_URL || "http://127.0.0.1:8000").replace(/\/$/, "");
let cookie = "";

async function request(path, options = {}, expectedStatus = 200) {
  const response = await fetch(`${baseUrl}${path}`, {
    ...options,
    headers: {...(options.headers || {}), ...(cookie ? {Cookie: cookie} : {})},
  });
  if (response.status !== expectedStatus) {
    throw new Error(`${path} returned HTTP ${response.status}: ${await response.text()}`);
  }
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
if (!cookie) throw new Error("login did not issue a session cookie");

const page = await (await request("/orders/")).text();
const script = await (await request("/orders/orders.js")).text();
for (const marker of ['id="status-tabs"', 'id="orders-list"', 'id="order-detail"', 'id="assistant-panel"']) {
  if (!page.includes(marker)) throw new Error(`order center missing ${marker}`);
}
for (const forbidden of ["cancel_pending_order", "return_delivered_order_items", "exchange_delivered_order_items"]) {
  if (page.includes(forbidden) || script.includes(`/api/v1/${forbidden}`)) {
    throw new Error(`order center exposes direct write path: ${forbidden}`);
  }
}

const index = await (await request("/api/v1/orders")).json();
if (!Array.isArray(index.orders) || index.orders.length === 0) throw new Error("customer order list is empty");
if (index.counts.all !== index.orders.length) throw new Error("order count does not match the returned list");

const selected = index.orders.find((order) => order.available) || index.orders[0];
const encodedOrderId = encodeURIComponent(selected.order_id);
const detail = await (await request(`/api/v1/orders/${encodedOrderId}`)).json();
if (detail.order_id !== selected.order_id || !Array.isArray(detail.items)) {
  throw new Error("order detail does not match the selected owned order");
}

const assistant = await (await request(`/api/v1/orders/${encodedOrderId}/assistant`, {
  method: "POST",
  headers: {"Content-Type": "application/json"},
  body: JSON.stringify({}),
})).json();
if (!assistant.conversation_id || assistant.order_id !== selected.order_id) {
  throw new Error("order assistant did not bind the selected order");
}

const conversation = await (await request(`/api/v1/support/conversations/${assistant.conversation_id}`)).json();
if (conversation.conversation_id !== assistant.conversation_id) {
  throw new Error("bound assistant conversation could not be restored");
}

await request("/api/v1/orders/%23W4140680", {}, 404);
await request(`/api/v1/support/conversations/${assistant.conversation_id}`, {method: "DELETE"}, 204);

console.log(`Order center acceptance passed: ${index.orders.length} owned orders; assistant ${assistant.conversation_id}`);
