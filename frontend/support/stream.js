export async function parseSSEStream(readable, onEvent) {
  if (!readable) throw new Error("浏览器未收到流式响应。");
  const reader = readable.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";
  let terminal = false;

  function consume(frame) {
    const lines = frame.replaceAll("\r\n", "\n").split("\n");
    let id = "";
    let event = "message";
    const data = [];
    for (const line of lines) {
      if (!line || line.startsWith(":")) continue;
      const separator = line.indexOf(":");
      const field = separator < 0 ? line : line.slice(0, separator);
      const value = separator < 0 ? "" : line.slice(separator + 1).replace(/^ /, "");
      if (field === "id") id = value;
      else if (field === "event") event = value;
      else if (field === "data") data.push(value);
    }
    if (!data.length) return;
    try {
      onEvent({ id, event, data: JSON.parse(data.join("\n")) });
      if (["completed", "error", "handoff"].includes(event)) terminal = true;
    } catch (error) {
      if (!(error instanceof SyntaxError)) throw error;
    }
  }

  while (true) {
    const { value, done } = await reader.read();
    buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
    const normalized = buffer.replaceAll("\r\n", "\n");
    const frames = normalized.split("\n\n");
    buffer = frames.pop() || "";
    frames.forEach(consume);
    if (done) break;
  }
  if (buffer.trim()) consume(buffer);
  if (!terminal) throw new Error("Stream ended without a terminal SSE event.");
}
