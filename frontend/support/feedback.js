export function createFeedbackPanel(root, api, getConversationId) {
  const negativeCategories = ["incorrect", "unclear", "slow", "tool_failure", "other"];
  const detail = root.querySelector("#feedback-detail");
  const status = root.querySelector("#feedback-status");
  let rating = null;
  async function submitFeedback(payload) {
    const conversationId = getConversationId();
    if (!conversationId) return;
    root.querySelectorAll("button").forEach((button) => button.disabled = true);
    status.textContent = "正在提交";
    try {
      await api.submitFeedback(conversationId, payload);
      status.textContent = "感谢您的反馈，我们已经记录。";
      detail.hidden = true;
    } catch (error) { status.textContent = error.message; }
    finally { root.querySelectorAll("button").forEach((button) => button.disabled = false); }
  }
  root.querySelectorAll("[data-feedback-rating]").forEach((button) => button.addEventListener("click", () => {
    rating = button.dataset.feedbackRating;
    if (rating === "helpful") submitFeedback({rating, category:"resolved"});
    else { detail.hidden = false; detail.querySelector("textarea").focus(); }
  }));
  detail.addEventListener("submit", (event) => {
    event.preventDefault();
    const category = detail.querySelector("select").value;
    if (!negativeCategories.includes(category)) return;
    submitFeedback({rating, category, comment:detail.querySelector("textarea").value.trim() || null});
  });
  return {show() { root.hidden = !getConversationId(); }, submitFeedback};
}
