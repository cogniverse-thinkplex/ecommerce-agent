const BASE = "/api/v1/support";
import { parseSSEStream } from "/support/stream.js?v=20261023-streaming";

async function request(path, options = {}) {
  let response;
  try {
    response = await fetch(`${BASE}${path}`, {headers:{"Content-Type":"application/json",...(options.headers||{})},...options});
  } catch (error) {
    reportClientError("NETWORK_FAILURE", path, null);
    throw error;
  }
  if (!response.ok) {
    if (response.status === 401) {
      window.location.replace("/login/");
      throw new Error("登录状态已失效，请重新登录。");
    }
    let detail = null;
    try { detail = (await response.json()).detail; } catch (_) { /* no body */ }
    if (response.status >= 500) reportClientError("SUPPORT_API_FAILURE", path, response.status);
    throw new Error(detail?.message || "服务暂时不可用，请稍后重试。");
  }
  return response.status === 204 ? null : response.json();
}

export const api = {
  createConversation: () => request("/conversations", { method: "POST" }),
  listConversations: (activeId = null) => request(`/conversations${activeId ? `?active_conversation_id=${encodeURIComponent(activeId)}` : ""}`),
  getConversation: (id) => request(`/conversations/${id}`),
  listMessages: (id) => request(`/conversations/${id}/messages`),
  archiveConversation: (id) => request(`/conversations/${id}`, { method: "DELETE" }),
  updateConversation: (id, payload) => request(`/conversations/${id}`, {method:"PATCH", body:JSON.stringify(payload)}),
  listGroups: () => request("/conversation-groups"),
  createGroup: (name) => request("/conversation-groups", {method:"POST", body:JSON.stringify({name})}),
  renameGroup: (id, name) => request(`/conversation-groups/${id}`, {method:"PATCH", body:JSON.stringify({name})}),
  deleteGroup: (id) => request(`/conversation-groups/${id}`, {method:"DELETE"}),
  sendMessage: (id, content) => request(`/conversations/${id}/messages`, {
    method: "POST", body: JSON.stringify({ content, request_id: crypto.randomUUID() }),
  }),
  streamMessage: async (id, content, requestId, onEvent) => {
    let response;
    try {
      response = await fetch(`${BASE}/conversations/${id}/messages/stream`, {
        method: "POST",
        headers: {"Content-Type": "application/json", "Accept": "text/event-stream"},
        body: JSON.stringify({content, request_id: requestId}),
      });
    } catch (error) {
      reportClientError("STREAM_NETWORK_FAILURE", `/conversations/${id}/messages/stream`, null);
      throw error;
    }
    if (response.status === 401) {
      window.location.replace("/login/");
      throw new Error("登录状态已失效，请重新登录。");
    }
    if (!response.ok) {
      let detail = null;
      try { detail = (await response.json()).detail; } catch (_) { /* no body */ }
      throw new Error(detail?.message || "流式客服暂时不可用，请稍后重试。");
    }
    await parseSSEStream(response.body, onEvent);
  },
  decideAction: (conversationId, actionId, decision) => request(
    `/conversations/${conversationId}/actions/${actionId}/${decision}`,
    { method: "POST", body: JSON.stringify({ request_id: crypto.randomUUID() }) },
  ),
  submitFeedback: (id, payload) => request(`/conversations/${id}/feedback`, {method:"POST", body:JSON.stringify(payload)}),
  listFeedback: (id) => request(`/conversations/${id}/feedback`),
  submitIssueFeedback: (payload) => request("/feedback", {method:"POST", body:JSON.stringify(payload)}),
  createHandoff: (id, message = null) => request(`/conversations/${id}/handoff`, {
    method: "POST",
    body: JSON.stringify({reason: "customer_requested", message}),
  }),
  getHandoff: async (id) => {
    const response = await fetch(`${BASE}/conversations/${id}/handoff`);
    if (response.status === 404) return null;
    if (!response.ok) throw new Error("无法读取人工服务状态。");
    return response.json();
  },
};

function reportClientError(errorCode, path, statusCode) {
  fetch("/api/v1/observability/client-errors", {method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({error_code:errorCode,summary:"客服请求失败",path,status_code:statusCode,severity:"error"})}).catch(() => {});
}
