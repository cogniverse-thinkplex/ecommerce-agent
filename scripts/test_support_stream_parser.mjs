import assert from "node:assert/strict";
import { parseSSEStream } from "../frontend/support/stream.js";

function readable(chunks) {
  return new ReadableStream({
    start(controller) {
      chunks.forEach((chunk) => controller.enqueue(chunk));
      controller.close();
    },
  });
}

const encoder = new TextEncoder();
const events = [];
const source = [
  "id: 1\nevent: accepted\ndata: {\"request_id\":\"r1\"}\n\n",
  ": heartbeat\n\n",
  "id: 2\nevent: progress\ndata: {\"message\":\"正在查询订单\"}\n\n",
  "id: 3\nevent: completed\ndata: {\"block_count\":1}\n\n",
].join("");
const bytes = encoder.encode(source);
const splitAt = source.indexOf("查") > 0 ? encoder.encode(source.slice(0, source.indexOf("查"))).length + 1 : 17;
await parseSSEStream(
  readable([bytes.slice(0, 11), bytes.slice(11, splitAt), bytes.slice(splitAt)]),
  (event) => events.push(event),
);

assert.deepEqual(events.map((event) => event.event), ["accepted", "progress", "completed"]);
assert.equal(events[1].data.message, "正在查询订单");
assert.deepEqual(events.map((event) => event.id), ["1", "2", "3"]);

const malformed = [];
await parseSSEStream(
  readable([
    encoder.encode("event: progress\ndata: not-json\n\nevent: completed\ndata: {}\n\n"),
  ]),
  (event) => malformed.push(event),
);
assert.deepEqual(malformed.map((event) => event.event), ["completed"]);

await assert.rejects(
  parseSSEStream(
    readable([encoder.encode("event: progress\ndata: {\"message\":\"still working\"}\n\n")]),
    () => {},
  ),
  /terminal SSE event/,
);

console.log("Support SSE parser tests passed");
