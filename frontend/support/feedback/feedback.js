import { api } from "/support/api.js?v=20261022";

const form = document.querySelector("#feedback-form");
const category = document.querySelector("#feedback-category");
const conversation = document.querySelector("#feedback-conversation");
const description = document.querySelector("#feedback-description");
const counter = document.querySelector("#character-count");
const status = document.querySelector("#feedback-status");

description.addEventListener("input", () => { counter.textContent = `${description.value.length} / 2000`; });

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const comment = description.value.trim();
  if (!comment) { status.textContent = "请填写问题描述。"; description.focus(); return; }
  const button = form.querySelector("button[type=submit]");
  button.disabled = true; status.textContent = "正在提交…";
  try {
    await api.submitIssueFeedback({
      category: category.value,
      comment,
      conversation_id: conversation.value || null,
    });
    form.reset(); counter.textContent = "0 / 2000";
    status.textContent = "反馈已提交，感谢您的帮助。";
  } catch (error) { status.textContent = error.message; }
  finally { button.disabled = false; }
});

(async () => {
  const data = await api.listConversations();
  data.conversations.forEach((item) => {
    const option = document.createElement("option");
    option.value = item.conversation_id;
    option.textContent = item.title;
    conversation.append(option);
  });
})().catch((error) => { status.textContent = error.message; });
