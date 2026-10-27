const shell = document.querySelector("[data-customer-shell]");

if (shell) {
  const back = shell.dataset.back || "/support/";
  const backLabel = shell.dataset.backLabel || "返回客服中心";
  const title = shell.dataset.title || document.title;
  shell.className = "customer-header";
  shell.innerHTML = `<a class="customer-back" href="${back}">← ${backLabel}</a><strong class="customer-page-title"></strong>`;
  shell.querySelector(".customer-page-title").textContent = title;
}

function stateMarkup(kind, title, message, actionLabel = "") {
  const action = actionLabel ? `<button class="customer-state-action" type="button">${actionLabel}</button>` : "";
  return `<div class="customer-state customer-state-${kind}" role="${kind === "error" ? "alert" : "status"}"><span class="customer-state-icon" aria-hidden="true"></span><strong>${title}</strong><small>${message || ""}</small>${action}</div>`;
}

export function renderLoading(host, message = "正在加载…") {
  host.innerHTML = stateMarkup("loading", message, "");
}

export function renderEmpty(host, title = "暂无内容", message = "") {
  host.innerHTML = stateMarkup("empty", title, message);
}

export function renderError(host, message, retry) {
  host.innerHTML = stateMarkup("error", "读取失败", message || "请稍后重试。", retry ? "重试" : "");
  if (retry) host.querySelector(".customer-state-action").addEventListener("click", retry);
}

window.CustomerUI = {renderLoading, renderEmpty, renderError};
