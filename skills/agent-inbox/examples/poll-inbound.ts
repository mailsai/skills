// Handle inbound email by polling, for agents that cannot receive webhooks.
// Run once:   MAILS_API_KEY=mk_test_... ALLOWED_SENDERS=you@example.com npx tsx poll-inbound.ts --once
// Keep going: the same command without --once. It polls every 15 seconds.
//
// The position is saved in STATE_FILE (default ./mails-inbox-state.json), so a restart
// neither repeats nor skips mail. The policy settings are listed in handle-inbound.ts.
import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { createClient, type TypedEvent } from "@mailsai/sdk";
import { handleInbound, type Outcome } from "./handle-inbound.ts";
import { INBOUND_EVENT_TYPES } from "./inbox-policy.ts";

const mails = createClient(); // reads MAILS_API_KEY
const STATE_FILE = process.env.STATE_FILE ?? "./mails-inbox-state.json";
const POLL_SECONDS = 15;
// An event's `created_at` is set as it is written, but the event can be read only once that
// write is finished, so it can turn up after newer ones. Each poll starts this far before the
// newest `created_at` handled, and `handled` keeps what comes back from being handled twice.
const OVERLAP_MS = 10 * 60_000;

type State = { since: string; handled: string[] };

function loadState(): State {
  if (existsSync(STATE_FILE)) return JSON.parse(readFileSync(STATE_FILE, "utf8")) as State;
  // First run: start from now, in the form every `created_at` has.
  return { since: new Date().toISOString(), handled: [] };
}

/** Every inbound event created at or after `since`, oldest first. */
async function fetchInbound(since: string): Promise<TypedEvent[]> {
  const found: TypedEvent[] = [];
  for (const eventType of INBOUND_EVENT_TYPES) {
    let cursor: string | undefined;
    do {
      const page = await mails.events.list({ event_type: eventType, since, limit: 100, cursor });
      found.push(...page.data);
      cursor = page.has_more ? page.next_cursor : undefined;
    } while (cursor);
  }
  return found.sort((a, b) => String(a.created_at).localeCompare(String(b.created_at)));
}

async function pollOnce(state: State): Promise<State> {
  const handled = new Set(state.handled);
  let since = state.since;
  const from = new Date(Date.parse(state.since) - OVERLAP_MS).toISOString();
  for (const event of await fetchInbound(from)) {
    if (handled.has(event.id)) continue; // handled on an earlier poll and read again
    let outcome: Outcome;
    try {
      outcome = await handleInbound(event);
    } catch (error) {
      // Stop here. The position has not moved past this event, so the next poll tries it again.
      console.error(`${event.id} failed:`, error);
      break;
    }
    console.log(`${event.id} ${outcome.action}: ${outcome.detail}`);
    handled.add(event.id);
    if (event.created_at && event.created_at > since) since = event.created_at;
    // Save after every event, so a crash repeats at most the one in progress.
    writeFileSync(STATE_FILE, JSON.stringify({ since, handled: [...handled].slice(-500) }));
  }
  return { since, handled: [...handled].slice(-500) };
}

async function main(): Promise<void> {
  let state = loadState();
  if (process.argv.includes("--once")) {
    await pollOnce(state);
    return;
  }
  for (;;) {
    state = await pollOnce(state);
    await new Promise((resolve) => setTimeout(resolve, POLL_SECONDS * 1000));
  }
}

main().catch((error: unknown) => {
  console.error(error);
  process.exit(1);
});
