const LABELS = {
  order_id: "订单号", status: "状态", items: "商品", address: "地址",
  payment_method: "支付方式", product_id: "商品编号", name: "名称",
  variants: "可选规格", email: "邮箱", orders: "订单", reason: "原因",
  item_ids: "商品项", new_item_ids: "替换商品", city: "城市", state: "州/省",
  country: "国家", zip: "邮编", address1: "地址", address2: "补充地址",
  action: "操作", order_status: "订单状态",
};

const STATUS_LABELS = {
  succeeded: "成功", failed: "失败", rejected: "已拒绝",
  pending: "待处理", processed: "处理中", shipped: "已发货",
  delivered: "已送达", cancelled: "已取消", returned: "已退货",
  exchanged: "已换货",
};

function valueText(value) {
  if (value == null) return "-";
  if (typeof value === "string" || typeof value === "number") return String(value);
  return JSON.stringify(value, null, 2);
}

function addressText(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) return valueText(value);
  return [value.address1, value.address2, value.city, value.state, value.zip, value.country]
    .filter(Boolean)
    .join("，");
}

function itemList(items) {
  const list = document.createElement("ul");
  list.className = "item-list";
  items.forEach((item) => {
    const row = document.createElement("li");
    const name = document.createElement("strong");
    name.textContent = item?.name || "商品";
    const meta = document.createElement("span");
    const options = item?.options && typeof item.options === "object"
      ? Object.values(item.options).filter(Boolean).join(" / ")
      : "";
    const parts = [item?.item_id ? `商品项 ${item.item_id}` : "", options];
    if (item?.price != null) parts.push(`$${Number(item.price).toFixed(2)}`);
    meta.textContent = parts.filter(Boolean).join(" · ");
    row.append(name, meta);
    list.append(row);
  });
  return list;
}

function valueNode(key, value) {
  if (key === "items" && Array.isArray(value)) return itemList(value);
  const span = document.createElement("span");
  span.textContent = key === "address"
    ? addressText(value)
    : (key === "status" || key === "order_status")
      ? (STATUS_LABELS[value] || valueText(value))
      : valueText(value);
  return span;
}

function details(data, excluded = ["action_id", "verification"]) {
  const dl = document.createElement("dl");
  dl.className = "detail-grid";
  Object.entries(data || {}).filter(([key]) => !excluded.includes(key)).forEach(([key, value]) => {
    const dt = document.createElement("dt");
    const dd = document.createElement("dd");
    dt.textContent = LABELS[key] || key;
    dd.append(valueNode(key, value));
    dl.append(dt, dd);
  });
  return dl;
}

export function createCard(block, onDecision) {
  const article = document.createElement("article");
  article.className = "business-card";
  const heading = document.createElement("h2");
  heading.textContent = block.title || "信息";
  article.append(heading);
  if (block.text) {
    const text = document.createElement("p");
    text.textContent = block.text;
    article.append(text);
  }
  if (block.type === "policy_citations") {
    article.classList.add("policy-card");
    const list=document.createElement("ul");list.className="policy-citation-list";
    (block.data?.citations||[]).forEach(item=>{const row=document.createElement("li");const link=document.createElement("a");link.href=item.source_url;link.target="_blank";link.rel="noopener";link.textContent=item.title||"政策来源";const summary=document.createElement("p");summary.textContent=item.content||"";const meta=document.createElement("small");meta.textContent=`适用范围：${item.scope||"以规则详情为准"} · 核验：${item.verified_at||"-"}`;row.append(link,summary,meta);list.append(row);});article.append(list);
  } else article.append(details(block.data));

  if (block.type === "confirmation") {
    article.classList.add("confirmation-card");
    const scope = document.createElement("p");
    scope.className = "confirmation-scope";
    scope.textContent = "确认仅授权本次操作一次；内容变化后需要重新确认。";
    article.append(scope);
    const actions = document.createElement("div");
    actions.className = "card-actions";
    const confirm = document.createElement("button");
    confirm.type = "button"; confirm.className = "confirm-button"; confirm.textContent = "确认执行";
    const reject = document.createElement("button");
    reject.type = "button"; reject.className = "reject-button"; reject.textContent = "拒绝操作";
    const actionId = block.data?.action_id;
    if (!actionId) { confirm.disabled = true; reject.disabled = true; }
    [confirm, reject].forEach((button) => button.addEventListener("click", async () => {
      confirm.disabled = true; reject.disabled = true;
      await onDecision(actionId, button === confirm ? "confirm" : "reject");
    }));
    actions.append(confirm, reject); article.append(actions);
  }
  if (block.type === "operation_result") {
    article.classList.add("result-card", block.data?.status === "succeeded" ? "success" : "failed");
  }
  return article;
}
