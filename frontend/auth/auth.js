const form = document.querySelector("#auth-form");
const errorNode = document.querySelector("#form-error");
const page = document.body.dataset.page;

document.querySelectorAll("[data-password-toggle]").forEach((toggle) => {
  toggle.addEventListener("click", () => {
    const input = document.getElementById(toggle.dataset.passwordToggle);
    if (!input) return;
    const willShow = input.type === "password";
    input.type = willShow ? "text" : "password";
    toggle.setAttribute("aria-pressed", String(willShow));
    toggle.setAttribute("aria-label", `${willShow ? "隐藏" : "显示"}${passwordName(input.id)}`);
    toggle.querySelector("span").textContent = willShow ? "隐藏" : "显示";
    input.focus();
  });
});

form?.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!form.reportValidity()) return;
  const button = form.querySelector("button[type=submit]");
  const values = Object.fromEntries(new FormData(form));
  errorNode.hidden = true;
  if (values.password_confirm !== undefined) {
    const primary = values.password ?? values.new_password;
    if (primary !== values.password_confirm) return showError("两次输入的密码不一致。");
    delete values.password_confirm;
  }
  const endpoint = {
    login: "/api/v1/auth/login",
    register: "/api/v1/auth/register",
    "change-password": "/api/v1/auth/change-password",
  }[page];
  setPending(button, true);
  try {
    const response = await fetch(endpoint, {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(values),
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail?.message || "请求未完成，请检查输入。");
    window.location.assign(payload.redirect_to);
  } catch (error) {
    showError(error.message);
    setPending(button, false);
  }
});

function setPending(button, pending) {
  const label = pending ? button.dataset.pendingLabel : button.dataset.label;
  button.disabled = pending;
  button.setAttribute("aria-busy", String(pending));
  button.querySelector("span").textContent = label;
}

function passwordName(id) {
  return ({password: "密码", "current-password": "当前密码", "new-password": "新密码", "password-confirm": "确认密码"})[id] || "密码";
}

function showError(message) {
  errorNode.textContent = message;
  errorNode.hidden = false;
  errorNode.focus();
}
