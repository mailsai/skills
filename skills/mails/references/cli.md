# The `mails` command line

The CLI is the npm package `@mailsai/cli`, which installs a `mails` command. It needs
Node.js 20 or newer.

```bash
npm install -g @mailsai/cli
mails login
```

## Sign in

- `mails login` opens your browser to approve the CLI and saves the sign-in as a profile.
  The sign-in comes back to this computer, so run it where your browser is.
- The CLI can do no more than your role in the workspace allows. Signed in by a member, it
  can send and read but cannot create API keys or webhooks. Signed in by a billing member, it
  can only read. If your role changes later, what the CLI can do changes with it.
- Sign in on each computer; do not copy the profile. A renewal works once, so when a copy
  renews too, mails.ai ends the sign-in. It then revokes the API keys and deletes the
  webhooks made with it, and gives a new signing secret to any other webhook whose secret it
  was shown. Rotate that webhook's secret to get one you can use.
- `mails login --api-key` asks for an API key instead. Use it on a server, in CI, or on a
  machine without a browser.
- The CLI uses, in order: the `--api-key` flag, `MAILS_API_KEY`, then the saved profile.
- `mails auth list`, `mails auth switch` and `mails auth remove` manage profiles.
  `mails whoami` shows which key, workspace and agent the CLI is using.

A browser sign-in acts in live mode: mail you send with it is delivered. To try commands
without sending anything, use a test key for them: `MAILS_API_KEY=mk_test_... mails ...`.

## Output for agents and scripts

- When its output is not a terminal, the CLI prints JSON. `--json` forces it.
- In JSON mode an error goes to stderr as an `error` object with `code` and `message`, and
  the exit code is 1.
- `mails commands --json` lists every command with its flags, the API route behind it and
  the key scope it needs. Commands follow the API's operations, grouped by resource, for
  example `emails`, `receiving`, `agents`, `threads`, `labels`, `search`, `drafts`,
  `events`, `webhooks`, `domains`, `api-keys` and `suppressions`.
- `--dry-run` prints the HTTP request instead of sending it. A command that is not one API
  request, such as `mails login` or `mails webhooks listen`, refuses it and does nothing.
  `--all` follows pagination to the end.
- The commands that send (`mails emails send`, `mails emails batch`, `mails emails reply`,
  `mails emails forward` and `mails drafts send`) take `--idempotency-key`. Without it the
  CLI makes up a key for each run, which protects its own retries of that run but not a
  second run of the command. In a script that may run twice, pass a key built from what
  makes the message unique:
  `mails emails reply rcv_01JABC --text-file ./reply.txt --idempotency-key reply-evt_01JABC`.
- Delete, revoke and archive commands ask first in a terminal and need `--yes` anywhere else.
  `mails threads delete` moves a thread to trash without asking. With `--permanent`, which
  deletes it for good, it asks like the others.

```bash
mails receiving list --json
mails events tail --type message.received --count 1 --json
mails receiving wait --from github.com --has code --json | jq -r '.message.codes[0].value'
```

The second command waits for one received message, prints it and exits. The third waits up to
30 seconds (`--timeout`, at most 50) for a sign-up code from GitHub and prints the code. Add
`--to` with the address the agent signed up with, such as a plus address
(`--to support.acme+github@in.mails.ai`), to wait only for mail sent there.

## Useful commands

- `mails webhooks listen --forward-to http://localhost:3000/webhooks` receives events and
  forwards each one to a local server with the body, headers and signature of a real
  delivery. It signs with `MAILS_WEBHOOK_SECRET` when that is set, so give it the secret
  your handler uses. Otherwise it makes a secret for the session and prints it. Without
  `--events` it forwards what an endpoint on `*` is sent, so not the thread events or
  `message.delayed`. Pass `--events` with your endpoint's types to forward exactly those.
- `mails events tail` follows new events. `--position-file <path>` on it, on
  `mails receiving listen` and on `mails webhooks listen` starts each run where the last one
  that used the file stopped, and keeps the place saved there: runs one after another miss
  no event and repeat none.
- `mails mcp install --client claude-code` adds the mails.ai MCP server to a client. The
  other clients are `claude`, `cursor`, `codex` and `vscode`. For `claude` it opens Claude's
  Add custom connector form with the server filled in, or prints the link when its output is
  not a terminal. The client signs in through the browser; `--auth key` makes Claude Code,
  Cursor and Codex read `MAILS_API_KEY` instead, for a machine with no browser. With it VS
  Code asks for the key once and keeps it in its own secret storage, and `claude` still signs
  in through the browser. The command never writes a key into a config file, and `--print`
  shows the change without making it. When the `claude` or `code` command it would run is not
  installed, it prints that command instead, and VS Code with `--auth key` gets the config to
  paste unless you add `--scope project`. In each of these cases, and for `claude`, its JSON
  output says `changed: false`.
