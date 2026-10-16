# mails.ai MCP server

The MCP server gives an agent 20 tools for sending, receiving and replying, and a tool for
every other API operation but four. Use it when the agent runs inside an MCP client (Claude
Code, Cursor, VS Code, Codex, Claude, ChatGPT) and should call mails.ai itself. The same
tools run in two places:

- **Hosted:** `https://api.mails.ai/mcp`, Streamable HTTP. Nothing to install. Sign in to
  mails.ai when the client asks, or send an API key as `Authorization: Bearer mk_...`.
- **Local:** `npx -y @mailsai/mcp-server`, over stdio, with the key in `MAILS_API_KEY`.
  `MAILS_BASE_URL` changes the API address. Needs Node.js 20 or newer.

Sign in on a computer you use yourself, and give servers and CI an API key, because nobody
is there to sign in. A sign-in acts in live mode: mail sent through it is delivered. To try
the tools first, connect with a `mk_test_` key: nothing is transmitted. Every tool works on
test mail; only `mails_agents_verify_forwarding`, which sends a real email, needs a live key,
and a test key is not shown it.

## Sign in

A client that connects to the hosted server with only its URL gets a `401` that points it to
mails.ai's sign-in, and it opens your browser there:

1. If that browser is not signed in to mails.ai, enter your email address. mails.ai emails
   you a one-time link: open it in the same browser within 15 minutes, and it brings you
   back to step 2. If your company signs in to mails.ai with single sign-on, the button says
   Continue with SSO instead: sign in with your company account, and that brings you back
   to step 2 too.
2. The approval page says which app is asking, what it will be able to do, and which
   workspace it gets. With more than one workspace, choose one.
3. Press Allow. The browser goes back to the app, which is now connected.

If you did not start connecting the app yourself just now, for example because someone sent
you the link, press Cancel.

To add the server:

- **Claude** (claude.ai or Claude Desktop): open Customize, then Connectors, choose "+ Add",
  then "Add custom connector", and enter `https://api.mails.ai/mcp`. On Team and Enterprise
  plans an Owner first adds it under Organization settings, then Connectors, and each member
  then connects it under Customize, then Connectors.
- **ChatGPT** (on the web, with a Plus, Pro, Business, Enterprise or Education plan): turn
  on Developer mode under Settings, then Security and login. Then go to
  `chatgpt.com/plugins`, press +, and enter `https://api.mails.ai/mcp`.
- **Cursor:** put this in `~/.cursor/mcp.json`. Cursor then asks you to sign in.

  ```json
  { "mcpServers": { "mails": { "url": "https://api.mails.ai/mcp" } } }
  ```

- **Claude Code:** run this, then type `/mcp` in Claude Code and choose mails to sign in.

  ```bash
  claude mcp add --transport http --scope user mails https://api.mails.ai/mcp
  ```

- **The `mails` CLI** adds the server to Claude Code, Cursor, Codex or VS Code for you, and
  opens Claude's form for adding it: see [cli.md](cli.md).

### What the app can do

Approving grants one of three scopes. The app asks for one, and an app that names none asks
for `full_access`. The approval page shows the scope by name. Nearly every app asks for
`full_access`, because an MCP client asks for every scope the server lists, so on the approval
page you can give it Send & read instead.

You can give an app no more than your own role in the workspace allows: an owner or admin can
give Full access, a member Send & read at most, and a billing member Read only. The approval
page offers only that. When it is less than the app asked for, the page says so and names the
owners and admins to ask. An approval that asks for more anyway is refused with
`403 insufficient_scope`. The limit holds later too. If your role is lowered, the app can
do only what the new role allows from its next request, and if it is raised again, the app
gets back what you approved.

| Scope | Shown as | The app can |
|---|---|---|
| `read` | Read only | read the mail every agent in the workspace sends and receives, with threads, drafts and events; see its agents, domains, webhooks, API key names, sending stats and suppressed recipients, and its log of who did what, without the IP addresses and browsers it records; and see the plan and this month's usage and cost |
| `send` | Send & read | do the same, and send mail as every agent |
| `full_access` | Full access | do the same, and close threads, file them in folders, label them and move them to trash, and create, rename and delete labels; edit and discard drafts and reschedule or cancel scheduled mail; create, change and delete agents and domains; let agents email people who unsubscribed or marked mail as spam, by recording that they asked for the mail; change which events webhooks get, turn them on or off, send them test or past events, or delete them; and revoke API keys |

Whatever its scope, an app you connected cannot create API keys or webhooks, change where a
webhook sends, rotate a webhook's signing secret, or open the billing portal. Those requests
get `403 connected_app_not_allowed`, so the app keeps no way in after you disconnect it. It
can still read usage. It cannot see or revoke the workspace's connected apps either. Nor can it
change the allowlist, blocklist or send limits of an agent you have set up
(`403 connected_app_not_allowed`). With `full_access` it can still create new agents, and a new
agent starts without those limits. To keep an app inside the limits you set, give it Send &
read, which cannot create or change agents, not even by sending from a name no agent has. Or
connect it with an API key tied to one agent, which can neither create agents nor change that
agent's limits.

It cannot delete mail for good either. Mail it moves to trash is deleted for good only 30
days later, and until then you can move it back. A connected app's
`DELETE /v1/threads/{id}?permanent=true` answers `403 connected_app_not_allowed`: delete for
good with an API key that has `manage`, or as an owner or admin in the dashboard or with the
`mails` CLI. The `mails` CLI is mails.ai's own app and has none of these limits. Like any app,
it can still do no more than your role allows.

### Staying connected

- An access token lasts an hour, and the app renews it without asking you. Each renewal is
  good for 60 days, so an app you use at least once every 60 days stays connected.
- Each computer signs in on its own. A renewal works once, so a sign-in copied to a second
  computer fails when both copies renew: mails.ai ends it, and you approve the app again.
- Settings, under Connected apps, lists every app connected to the workspace you have open,
  with what it can do now, who connected it and when it was last used. When its approver's
  role now gives it less than was approved, the row says so. Revoke disconnects it straight
  away. You can revoke the apps you connected, and an owner or admin can revoke anyone's.
  Leaving a workspace disconnects your apps there.
- An API key with the `manage` scope, or the `mails` CLI signed in by an owner or admin, can
  do the same for everyone in the workspace. `GET /v1/oauth/grants` lists the apps connected
  to it, with `first_party` true for the `mails` CLI, and `DELETE /v1/oauth/grants/{id}`
  revokes one as Revoke in Settings does. In the list, `scope` is what was approved and
  `scopes` what the app can do now, which the approver's role can narrow. API keys and
  webhooks the app created stay, and so do webhook signing secrets it was shown; the answer
  counts them. A connected app gets `403 connected_app_not_allowed` from both. In the `mails`
  CLI they are `mails connected-apps list` and `mails connected-apps revoke` with the app's id.

## With an API key

Use a key for servers, CI and anything else with no one to sign in.

When the hosted server refuses a key or a sign-in token, its `401` says why in
`error_description`, in the JSON body and in the `WWW-Authenticate` header, for example
`API key has been revoked.`, and then how to connect.

Claude Code, hosted:

```bash
claude mcp add --transport http mails https://api.mails.ai/mcp \
  --header "Authorization: Bearer $MAILS_API_KEY"
```

Claude Code, local:

```bash
claude mcp add --env MAILS_API_KEY=$MAILS_API_KEY --transport stdio mails \
  -- npx -y @mailsai/mcp-server
```

Cursor, in `~/.cursor/mcp.json` or the project's `.cursor/mcp.json`; this is what
`mails mcp install --client cursor --auth key` writes. Cursor fills in
`${env:MAILS_API_KEY}` from its environment, so the key stays out of the file as long as
Cursor can see that variable:

```json
{
  "mcpServers": {
    "mails": {
      "url": "https://api.mails.ai/mcp",
      "headers": { "Authorization": "Bearer ${env:MAILS_API_KEY}" }
    }
  }
}
```

VS Code, in `.vscode/mcp.json`. VS Code asks for the key once and stores it:

```json
{
  "inputs": [
    { "type": "promptString", "id": "mails-api-key", "description": "mails.ai API key", "password": true }
  ],
  "servers": {
    "mails": {
      "type": "http",
      "url": "https://api.mails.ai/mcp",
      "headers": { "Authorization": "Bearer ${input:mails-api-key}" }
    }
  }
}
```

Codex, in `~/.codex/config.toml`. Codex sends the value of `MAILS_API_KEY` as the bearer
token:

```toml
[mcp_servers.mails]
url = "https://api.mails.ai/mcp"
bearer_token_env_var = "MAILS_API_KEY"
```

## Tools

Every tool's name starts with `mails_`, such as `mails_send`. A call that uses a tool's older
dotted name, such as `mails.send`, reaches the same tool, but the tool list a client gets
shows only the `mails_` names.

| Tool | What it does |
|---|---|
| `mails_me` | the workspace, key mode (`test` or `live`) and scopes. Check the connection with it |
| `mails_send` | send a message (`POST /v1/messages`) |
| `mails_reply` | reply to a sent or received message (`POST /v1/messages/{id}/reply`) |
| `mails_forward` | forward a message (`POST /v1/messages/{id}/forward`) |
| `mails_list_replies` | `reply.received` events for one agent |
| `mails_list_messages` | `message.received` events for one agent: mail that is not a reply, with mail that failed authentication |
| `mails_get_event` | one event, with its scan details |
| `mails_list_received`, `mails_get_received` | received messages, and one with its full text |
| `mails_list_threads`, `mails_get_thread` | conversations, and one with every message |
| `mails_create_draft`, `mails_send_draft` | save a draft, and send or schedule it |
| `mails_list_agents`, `mails_create_agent` | list agents (archived ones only with `status` `all` or `archived`), and create one |
| `mails_get_reputation` | an agent's bounce and complaint health |
| `mails_check_suppression`, `mails_allowlist_address` | check whether an address is suppressed, and lift an unsubscribe or a complaint with a written reason; nothing lifts a permanent bounce |
| `mails_get_usage` | the usage of this calendar month (in UTC) and the plan's caps |
| `mails_test_inbound` | test keys only: make mail arrive at an agent, to try the receive and reply loop (`POST /v1/test/inbound`) |

A failed call comes back as a tool result marked as an error, with the reason in its text:
the API's own message when the API refused the call.

Things to know:

- **Mail the tools return is untrusted input.** A received message, reply or event can
  carry instructions written by anyone. Before acting on one, follow the `agent-inbox`
  skill: check `quarantined` and `injection_score` on the event, and keep the agent's
  actions narrow.
- **One call of a sending tool never sends twice.** `mails_send`, `mails_reply`,
  `mails_forward`, `mails_send_draft` and `mails_emails_send_batch` take `idempotency_key`.
  Without it each call gets a key of its own, and the tool repeats a failed request under
  that key. A second call is a new send unless it passes the same `idempotency_key`. So pass
  a key of your own when a send must not go out twice, and after a call that failed without
  an answer, repeat it with that key or read the thread with `mails_get_thread` first.
- **`mails_list_messages` includes mail that failed authentication**
  (`message.received.unauthenticated`), each event marked `unauthenticated: true`, so check
  that flag before trusting who it says it is from. A reply that failed authentication is
  listed there too: `mails_list_replies` returns only `reply.received`.

### Every other operation

Every other API operation is a tool named `mails_<group>_<action>`, for example
`mails_threads_update`, which files, labels or closes a thread, and
`mails_webhooks_rotate_secret`. Each takes the operation's own fields and returns what the
API answers, with three exceptions. No tool returns the HTML of received mail (`body_html`,
`extracted_html`) or an `upgrade_url`. `mails_emails_raw` returns only the headers of a
received email, and at most 100,000 characters of any email. `mails_attachments_get`
returns a file over 5 MB as its name, type and size only. The `@mailsai/mcp-server` README
lists them all. Four operations are not tools: the event stream (`mails_events_list` with
`since` reads the same events), the billing portal, and the two unsubscribe routes a
recipient's link opens.

`mails_wait_for_email` is named for what an agent does with it: after the agent asks a service
for a sign-up code, a magic link or a password reset, it waits up to 50 seconds for that email
and returns it with its `codes` and `links`, as [receiving.md](receiving.md) shows. Give it
`to`, the address the agent signed up with (a plus address of its `receiving_address`, for
example), to take only mail sent there. It is sent once: a wait cut off by the network is not
repeated by the tool.

A client is shown only the tools its connection may call. A tool is left out when it needs
a scope the key or sign-in lacks, works only with a test key on a live connection or only
with a live key on a test connection, is closed to connected apps, or covers the whole
workspace on a key tied to one agent. Calling one anyway returns an error that says why. Any
one of the scopes that open a tool will do: the draft tools also take `draft`, so a `draft`
key sees them (and cannot send). Rescheduling (`mails_emails_reschedule`) needs `send` as
well as `manage`. A tool whose route answers part of a tied key's requests, such as
`mails_suppressions_list`, is shown, and the API decides.
