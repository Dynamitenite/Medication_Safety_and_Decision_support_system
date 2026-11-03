import assert from "node:assert/strict";
import test from "node:test";
import { createStatusCache } from "./answerStatusCache.ts";

const flush = () => new Promise((r) => setImmediate(r));

test("a not_ready answer is asked again after the retry window", async () => {
  let t = 0;
  const answers = ["not_ready", "ready"];
  let calls = 0;
  const get = createStatusCache(async () => ({ status: answers[calls++] }), () => t, 1000);
  assert.equal((await get()).status, "not_ready");
  await flush();
  t = 500;
  assert.equal((await get()).status, "not_ready");
  assert.equal(calls, 1);
  t = 1500;
  assert.equal((await get()).status, "ready");
  assert.equal(calls, 2);
});

test("a ready answer is kept for the session", async () => {
  let t = 0;
  let calls = 0;
  const get = createStatusCache(async () => (calls++, { status: "ready" }), () => t, 1000);
  await get();
  await flush();
  t = 10 ** 9;
  await get();
  assert.equal(calls, 1);
});

test("a failed request is retried at once", async () => {
  let calls = 0;
  const get = createStatusCache(async () => {
    if (calls++ === 0) throw new Error("down");
    return { status: "ready" };
  });
  await assert.rejects(get());
  await flush();
  assert.equal((await get()).status, "ready");
});
