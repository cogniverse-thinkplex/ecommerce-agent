const profileForm = document.querySelector("#profile-form");
const passwordForm = document.querySelector("#password-form");
const displayName = document.querySelector("#display-name");
const email = document.querySelector("#email");
const retailStatus = document.querySelector("#retail-status");

async function request(url, options = {}) {
  const response = await fetch(url, {credentials: "same-origin", ...options});
  if (response.status === 401) { window.location.replace("/login/"); throw new Error("请先登录。"); }
  const body = response.status === 204 ? null : await response.json();
  if (!response.ok) throw new Error(body?.detail?.message || "请求失败，请稍后重试。");
  return body;
}

profileForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const status = document.querySelector("#profile-status");
  try {
    const user = await request("/api/v1/auth/me", {
      method: "PATCH", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({display_name: displayName.value}),
    });
    displayName.value = user.display_name; status.textContent = "资料已保存。";
  } catch (error) { status.textContent = error.message; }
});

passwordForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const status = document.querySelector("#password-status");
  try {
    await request("/api/v1/auth/change-password", {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({
        current_password: document.querySelector("#current-password").value,
        new_password: document.querySelector("#new-password").value,
      }),
    });
    passwordForm.reset(); status.textContent = "密码已更新。";
  } catch (error) { status.textContent = error.message; }
});

function maskPhone(phone) { return phone ? `${phone.slice(0,3)}****${phone.slice(-4)}` : "待补充手机号"; }
async function loadAddresses() {
  const list = document.querySelector("#address-list");
  const addresses = await request("/api/v1/auth/addresses");
  list.replaceChildren();
  if (!addresses.length) { list.textContent = "暂无收货地址。"; return; }
  addresses.forEach((address) => {
    const card = document.createElement("article"); card.className = "address-card";
    card.innerHTML = `<header><strong></strong><span></span></header><p class="phone"></p><p class="full-address"></p><footer><a>编辑</a></footer>`;
    card.querySelector("strong").textContent = address.recipient_name;
    const badge = card.querySelector("header span"); badge.textContent = address.is_default ? "默认" : ""; badge.className = address.is_default ? "default-badge" : "";
    card.querySelector(".phone").textContent = maskPhone(address.phone);
    card.querySelector(".full-address").textContent = [address.country,address.state,address.city,address.address1,address.address2,address.zip].filter(Boolean).join(" ");
    card.querySelector("a").href = `/account/address/?id=${encodeURIComponent(address.address_id)}`;
    const footer = card.querySelector("footer");
    if (!address.is_default) {
      const setDefault = document.createElement("button"); setDefault.textContent = "设为默认";
      setDefault.addEventListener("click", async () => { await request(`/api/v1/auth/addresses/${address.address_id}/default`, {method:"POST"}); await loadAddresses(); });
      const remove = document.createElement("button"); remove.textContent = "删除"; remove.className = "danger";
      remove.addEventListener("click", async () => { if (window.confirm("确定删除这个地址吗？")) { await request(`/api/v1/auth/addresses/${address.address_id}`, {method:"DELETE"}); await loadAddresses(); } });
      footer.append(setDefault, remove);
    }
    list.append(card);
  });
}

(async () => {
  const user = await request("/api/v1/auth/me");
  if (user.role !== "customer") { window.location.replace("/dashboard/"); return; }
  displayName.value = user.display_name; email.value = user.email;
  retailStatus.textContent = user.retail_account_linked ? "已关联" : "未关联";
  if (user.retail_account_linked) {
    await loadAddresses();
  } else {
    document.querySelector("#address-status").textContent = "关联购买账户后可以管理收货地址。";
  }
})().catch((error) => { document.querySelector("#profile-status").textContent = error.message; });
