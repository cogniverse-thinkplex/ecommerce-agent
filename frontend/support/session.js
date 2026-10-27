const KEY = "ecom-support-conversation";
export const selectedConversation = {
  get: () => localStorage.getItem(KEY),
  set: (id) => localStorage.setItem(KEY, id),
  clear: () => localStorage.removeItem(KEY),
};
