import { api } from "/support/api.js?v=20261023-customer-shell";
import { selectedConversation } from "/support/session.js?v=20261022";
import { createChat } from "/support/chat.js?v=20261023-streaming";
import { renderGroupManager, renderHistoryList } from "/support/history.js?v=20261023-customer-shell";

if (new URLSearchParams(location.search).get("embed") === "1") {
  document.body.classList.add("embed-mode");
}

const els = {
  stream: document.querySelector("#message-stream"), list: document.querySelector("#conversation-list"),
  form: document.querySelector("#composer"), input: document.querySelector("#message-input"),
  send: document.querySelector("#send-button"), notice: document.querySelector("#notice"),
  newChat: document.querySelector("#new-chat"), panel: document.querySelector("#history-panel"),
  toggle: document.querySelector("#history-toggle"), scrim: document.querySelector("#drawer-scrim"),
  transfer: document.querySelector("#transfer-to-human"),
  handoffStatus: document.querySelector("#handoff-status"),
  manageGroups: document.querySelector("#manage-groups"), groupDialog: document.querySelector("#group-dialog"), groupManager: document.querySelector("#group-manager"),
  newGroupForm: document.querySelector("#new-group-form"), newGroupName: document.querySelector("#new-group-name"),
  moveDialog: document.querySelector("#move-conversation-dialog"), moveForm: document.querySelector("#move-conversation-form"),
  moveGroupSelect: document.querySelector("#move-group-select"), cancelMove: document.querySelector("#cancel-move-conversation"),
};
const pageParams = new URLSearchParams(location.search);
const embeddedConversationId = pageParams.get("conversation_id");
let activeId = embeddedConversationId || selectedConversation.get();
if (embeddedConversationId) selectedConversation.set(embeddedConversationId);
let busy = false;
let conversations = []; let groups = [];
let movingConversationId = null;
const sectionStateKey = "support.history.sections";
let sectionState = (() => { try { return JSON.parse(localStorage.getItem(sectionStateKey) || "{}"); } catch (_) { return {}; } })();
const chat = createChat(els.stream, decideAction, (text) => { els.input.value=text;els.input.focus(); });
const accountIdentity = document.querySelector("#sidebar-account-name");
const accountAvatar = document.querySelector("#sidebar-account-avatar");
const logoutButton = document.querySelector("#logout-button");

function showError(error) { els.notice.textContent = error.message; els.notice.hidden = false; }
function clearError() { els.notice.hidden = true; els.notice.textContent = ""; }
function setBusy(value) { busy = value; els.send.disabled = value; els.input.disabled = value; }
function closeDrawer() { els.panel.classList.remove("open"); els.scrim.hidden = true; }

async function refreshList() {
  const [data, groupData] = await Promise.all([api.listConversations(activeId), api.listGroups()]);
  conversations = data.conversations; groups = groupData.groups;
  drawHistory();
}

function drawHistory() {
  renderHistoryList(els.list, conversations, groups, activeId, {
    select: selectConversation,
    togglePin: async item => { await api.updateConversation(item.conversation_id,{is_pinned:!item.is_pinned}); await refreshList(); },
    rename: async item => { const title=window.prompt("输入新的会话名称",item.title); if(title?.trim()){await api.updateConversation(item.conversation_id,{title:title.trim()});await refreshList();} },
    move: openMoveDialog,
    remove: removeConversation,
    isSectionOpen: (id, fallback) => Object.hasOwn(sectionState, id) ? sectionState[id] : fallback,
    sectionOpen: (id, open) => { sectionState[id] = open; localStorage.setItem(sectionStateKey, JSON.stringify(sectionState)); },
  });
}

function openMoveDialog(item, available) {
  movingConversationId = item.conversation_id;
  els.moveGroupSelect.replaceChildren();
  const other = document.createElement("option"); other.value = ""; other.textContent = "其他会话"; els.moveGroupSelect.append(other);
  available.forEach(group => { const option=document.createElement("option");option.value=group.group_id;option.textContent=group.name;els.moveGroupSelect.append(option); });
  els.moveGroupSelect.value = item.group_id || "";
  els.moveDialog.showModal();
}

async function removeConversation(item) {
  if(!window.confirm("确定删除此会话吗？删除后不会在历史列表中显示。"))return;
  const previous = conversations;
  conversations = conversations.filter(conversation => conversation.conversation_id !== item.conversation_id);
  if(activeId===item.conversation_id){activeId=null;selectedConversation.clear();chat.empty();}
  drawHistory();
  try {
    await api.archiveConversation(item.conversation_id);
    await refreshList();
    if(!activeId&&conversations.length)await selectConversation(conversations[0].conversation_id);
  } catch (error) {
    conversations = previous; drawHistory(); showError(error);
  }
}
function drawGroupManager(){renderGroupManager(els.groupManager,groups,{rename:async group=>{const name=window.prompt("输入新的分组名称",group.name);if(name?.trim()){await api.renameGroup(group.group_id,name.trim());await refreshList();drawGroupManager();}},remove:async group=>{if(window.confirm(`确定删除分组“${group.name}”吗？组内会话将移到其他会话。`)){await api.deleteGroup(group.group_id);await refreshList();drawGroupManager();}}});}

async function createConversation() {
  clearError();
  const conversation = await api.createConversation();
  activeId = conversation.conversation_id; selectedConversation.set(activeId);
  await loadConversation(activeId); await refreshList(); els.input.focus();
}

async function selectConversation(id) {
  activeId = id; selectedConversation.set(id); closeDrawer();
  await loadConversation(id); await refreshList();
}

async function loadConversation(id) {
  try {
    const data = await api.listMessages(id);
    chat.renderHistory(data.messages);
    await refreshHandoff(id);
  } catch (error) {
    selectedConversation.clear(); activeId = null; chat.empty(); showError(error);
  }
}

function renderHandoff(ticket) {
  const labels = {open:"等待人工接入", in_progress:"人工处理中", resolved:"人工服务已结束", cancelled:"人工工单已取消"};
  els.handoffStatus.textContent = ticket ? labels[ticket.status] || "人工服务状态已更新" : "";
  els.transfer.disabled = Boolean(ticket && ["open", "in_progress"].includes(ticket.status));
}

async function refreshHandoff(id) {
  renderHandoff(await api.getHandoff(id));
}

async function sendMessage(event) {
  event.preventDefault();
  const content = els.input.value.trim();
  if (!content || busy) return;
  if (!activeId) await createConversation();
  clearError(); chat.appendText(content, "user"); els.input.value = ""; setBusy(true);
  const activity = chat.beginActivity();
  const requestId = crypto.randomUUID();
  try {
    await api.streamMessage(activeId, content, requestId, (event) => {
      if (event.event === "accepted" || event.event === "progress") {
        chat.updateActivity(activity, event);
      } else if (event.event === "block" || event.event === "confirmation_required") {
        chat.appendStreamBlock(event.data.block, requestId, event.data.index, activity);
      } else if (event.event === "error") {
        throw new Error(event.data.message || "客服处理失败，请稍后重试。");
      } else if (event.event === "completed") {
        chat.finishActivity(activity);
      } else if (event.event === "handoff") {
        chat.updateActivity(activity, {data:{message:event.data.message || "已申请人工服务"}});
        refreshHandoff(activeId).catch(() => {});
        chat.finishActivity(activity);
      }
    });
    await refreshList();
  } catch (error) {
    chat.finishActivity(activity);
    showError(error);
    await loadConversation(activeId).catch(() => {});
  }
  finally { chat.finishActivity(activity); setBusy(false); els.input.focus(); }
}

async function decideAction(actionId, decision) {
  if (!activeId || !actionId) return;
  clearError();
  try {
    const result = await api.decideAction(activeId, actionId, decision);
    result.blocks.forEach((block) => chat.appendBlock(block)); await refreshList();
  } catch (error) { showError(error); }
}

els.form.addEventListener("submit", sendMessage);
els.newChat.addEventListener("click", () => createConversation().catch(showError));
els.manageGroups.addEventListener("click",()=>{drawGroupManager();els.groupDialog.showModal();});
els.newGroupForm.addEventListener("submit",async event=>{event.preventDefault();const name=els.newGroupName.value.trim();if(!name)return;try{const group=await api.createGroup(name);sectionState[`group:${group.group_id}`]=true;localStorage.setItem(sectionStateKey,JSON.stringify(sectionState));els.newGroupName.value="";await refreshList();drawGroupManager();}catch(error){showError(error);}});
els.cancelMove.addEventListener("click",()=>els.moveDialog.close());
els.moveForm.addEventListener("submit",async event=>{event.preventDefault();if(!movingConversationId)return;const groupId=els.moveGroupSelect.value||null;try{await api.updateConversation(movingConversationId,{group_id:groupId});if(groupId){sectionState[`group:${groupId}`]=true;}else{sectionState.other=true;}localStorage.setItem(sectionStateKey,JSON.stringify(sectionState));els.moveDialog.close();movingConversationId=null;await refreshList();}catch(error){showError(error);}});
els.toggle.addEventListener("click", () => { els.panel.classList.add("open"); els.scrim.hidden = false; });
els.scrim.addEventListener("click", closeDrawer);
els.transfer.addEventListener("click", async () => {
  if (busy) return;
  try {
    if (!activeId) await createConversation();
    els.transfer.disabled = true;
    renderHandoff(await api.createHandoff(activeId, "客户从客服中心申请人工服务。"));
  } catch (error) { els.transfer.disabled = false; showError(error); }
});
els.input.addEventListener("input", () => {
  els.input.style.height = "auto";
  els.input.style.height = `${Math.min(els.input.scrollHeight, 140)}px`;
});
logoutButton.addEventListener("click", async () => {
  await fetch("/api/v1/auth/logout", {method: "POST"});
  window.location.assign("/login/");
});

(async function start() {
  try {
    const identityResponse = await fetch("/api/v1/auth/me", {credentials: "same-origin"});
    if (identityResponse.status === 401) { window.location.replace("/login/"); return; }
    if (!identityResponse.ok) throw new Error("无法读取登录账户。");
    const identity = await identityResponse.json();
    if (identity.role !== "customer") { window.location.replace("/dashboard/"); return; }
    accountIdentity.textContent = identity.display_name || identity.email;
    accountAvatar.textContent = (identity.display_name || identity.email || "客").trim().slice(0, 1).toUpperCase();
    await refreshList();
    if (activeId) await loadConversation(activeId); else chat.empty();
    const prompt = pageParams.get("prompt");
    if (prompt) { els.input.value = prompt; els.input.focus(); }
  } catch (error) { chat.empty(); showError(error); }
})();
