import { createCard } from "/support/cards.js?v=20261021";

export function createChat(stream, onDecision, onShortcut) {
  const activityTimers = new WeakMap();
  function clear() { stream.replaceChildren(); }
  function empty() {
    clear();
    const node = document.createElement("div"); node.className = "empty-state";
    const title = document.createElement("strong"); title.textContent = "开始一次客服会话";
    const text = document.createElement("span"); text.textContent = "请选择常用服务，或直接在下方描述您的问题。";
    const shortcuts = document.createElement("div"); shortcuts.className = "support-shortcuts";
    ["查询全部订单", "查询订单状态", "取消待处理订单", "办理退换货"].forEach(label => {
      const button=document.createElement("button");button.type="button";button.className="support-shortcut";button.textContent=label;button.addEventListener("click",()=>onShortcut(label));shortcuts.append(button);
    });
    node.append(title, text, shortcuts); stream.append(node);
  }
  function appendText(text, role = "assistant") {
    const row = document.createElement("div"); row.className = `message-row ${role}`;
    const bubble = document.createElement("div"); bubble.className = "bubble"; bubble.textContent = text;
    row.append(bubble); stream.append(row); stream.scrollTop = stream.scrollHeight;
  }
  function appendBlock(block) {
    if (block.type === "text") return appendText(block.text || "");
    const row = document.createElement("div"); row.className = "message-row assistant";
    row.append(createCard(block, onDecision)); stream.append(row); stream.scrollTop = stream.scrollHeight;
  }
  function appendPending() {
    const row = document.createElement("div");
    row.className = "message-row assistant pending-reply";
    row.setAttribute("aria-label", "客服正在处理");
    const bubble = document.createElement("div");
    bubble.className = "bubble";
    const label = document.createElement("span");
    label.textContent = "正在查询订单，请稍候";
    const dots = document.createElement("span");
    dots.className = "pending-dots";
    dots.setAttribute("aria-hidden", "true");
    dots.textContent = "...";
    bubble.append(label, dots); row.append(bubble); stream.append(row);
    stream.scrollTop = stream.scrollHeight;
    return row;
  }
  function removePending(row) { row?.remove(); }
  function beginActivity() {
    const row = document.createElement("div");
    row.className = "message-row assistant activity-row";
    row.setAttribute("role", "status");
    row.setAttribute("aria-live", "polite");
    const bubble = document.createElement("div"); bubble.className = "bubble";
    const label = document.createElement("span"); label.className = "activity-label";
    label.textContent = "请求已发送，等待客服处理";
    const elapsed = document.createElement("small"); elapsed.className = "activity-elapsed";
    elapsed.textContent = "0 秒";
    bubble.append(label, elapsed); row.append(bubble); stream.append(row);
    const started = Date.now();
    activityTimers.set(row, setInterval(() => {
      elapsed.textContent = `${Math.floor((Date.now() - started) / 1000)} 秒`;
    }, 1000));
    stream.scrollTop = stream.scrollHeight;
    return row;
  }
  function updateActivity(row, event) {
    if (!row?.isConnected) return;
    const data = event?.data || {};
    const progress = data.completed != null && data.total != null
      ? ` ${data.completed}/${data.total}` : "";
    row.querySelector(".activity-label").textContent = `${data.message || "正在处理"}${progress}`;
    stream.scrollTop = stream.scrollHeight;
  }
  function appendStreamBlock(block, requestId, index, activityRow) {
    const marker = `${index}`;
    if (stream.querySelector(`[data-stream-request="${requestId}"][data-stream-block="${marker}"]`)) return;
    const before = stream.lastElementChild;
    appendBlock(block);
    const row = stream.lastElementChild;
    row.dataset.streamBlock = marker;
    row.dataset.streamRequest = requestId;
    if (activityRow?.isConnected) stream.insertBefore(row, activityRow);
    else if (before?.classList.contains("activity-row")) stream.insertBefore(row, before);
  }
  function finishActivity(row) {
    const timer = activityTimers.get(row);
    if (timer) clearInterval(timer);
    activityTimers.delete(row);
    row?.remove();
  }
  function renderHistory(messages) {
    clear();
    messages.forEach((message) => {
      if (message.role === "user") appendText(message.text || "", "user");
      else if (message.payload?.type) appendBlock(message.payload);
      else if (message.text) appendText(message.text);
    });
    if (!messages.length) empty();
  }
  return {
    clear, empty, appendText, appendBlock, appendPending, removePending,
    beginActivity, updateActivity, appendStreamBlock, finishActivity, renderHistory,
  };
}
