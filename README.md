# mails.ai skills for AI agents

Three skills that teach an AI agent to send and receive email through mails.ai, and to act on
the mail it receives without being steered by the people who write it.

| Skill | Use it when |
|---|---|
| [`mails`](skills/mails/SKILL.md) | an agent needs its own email address: sending, receiving, replying, threads, drafts, webhooks, through the API, the TypeScript and Python SDKs or MCP |
| [`agent-inbox`](skills/agent-inbox/SKILL.md) | an agent reads incoming email and then replies, calls tools or changes anything because of it; covers five levels of protection and webhook signature checks |
| [`email-best-practices`](skills/email-best-practices/SKILL.md) | setting up a custom sending domain, handling bounces, complaints and unsubscribes, or checking what mails.ai refuses and what the law requires |

Each skill is a folder in the [Agent Skills](https://agentskills.io/specification) format:
`SKILL.md` (loaded when the skill is used), `references/` (read when needed) and `examples/`
(runnable TypeScript and Python).

## Install

As a Claude Code plugin, which brings the three skills and the hosted mails.ai MCP server
together. In Claude Code 2.1.275 or later:

```
/plugin install mails --marketplace mailsai/skills
```

In older versions, add the marketplace first, then install from it:

```
/plugin marketplace add mailsai/skills
/plugin install mails@mailsai
```

Then type `/mcp` and choose mails to sign in to mails.ai in your browser. From a terminal (Claude
Code 2.1.292 or later), the same is `claude plugin install mails --marketplace mailsai/skills`.

With the [skills](https://github.com/vercel-labs/skills) command:

```bash
npx skills add mailsai/skills
```

Add `--skill mails` to install one skill, `-a claude-code` to pick the agent, and `-g` to
install for your user instead of the current project.

Or copy the skill folders by hand. For Claude Code:

```bash
git clone https://github.com/mailsai/skills mails-skills
mkdir -p ~/.claude/skills
cp -R mails-skills/skills/mails mails-skills/skills/agent-inbox mails-skills/skills/email-best-practices ~/.claude/skills/
```

Use `.claude/skills/` inside a project instead of `~/.claude/skills/` to install for that
project only. Other agents read skills from their own folders; see their documentation.

## What the examples need

- A mails.ai API key in `MAILS_API_KEY`. Start with a test key (`mk_test_...`): nothing is
  delivered and nothing is billed.
- TypeScript: Node.js 18 or newer, `npm install @mailsai/sdk`, and `npx tsx <file>` to run.
- Python: Python 3.10 or newer and `pip install mailsai`. `rest.py` in each skill's
  `examples/` calls any endpoint that answers JSON with only the standard library, for code
  where the SDK is not installed.

## Agent Plugin

This folder is also an [Agent Plugin](https://agent-plugins.org), in version 1.0.0 of that
format: `plugin.json` describes it, `skills/` holds the skills, and `mcp.json` registers the
hosted mails.ai MCP server at `https://api.mails.ai/mcp`.

It is also a Claude Code plugin and its own marketplace: `.claude-plugin/plugin.json` describes
the plugin, `.claude-plugin/marketplace.json` lists it, and `.mcp.json` registers the same server
in Claude Code's format. The plugin has no `version`, so every commit to this repository is a
new version: `claude plugin update mails@mailsai` fetches the latest, and so does turning on
auto-update for the mailsai marketplace under `/plugin`.

`mcp.json` and `.mcp.json` hold only the server's address, never a key. A client that installs
the plugin connects to `https://api.mails.ai/mcp`, gets a `401` that points it to mails.ai's
sign-in, and opens your browser: sign in to mails.ai, choose the workspace and press Allow. In
Claude Code, type `/mcp` and choose mails to sign in. Each computer signs in on its own; on a
server or in CI, add the server with an API key instead. Both are in
[skills/mails/references/mcp.md](skills/mails/references/mcp.md).

## Checking the skills

In the mails.ai API repository, `npm run check:skills` checks every skill: the frontmatter
against the Agent Skills rules, every relative link, every API path against the OpenAPI
document, every example against the real SDKs (TypeScript type-checked, Python compiled and
imported, and both run against a local stand-in for the API), the webhook signature code
against known answers, the facts the skills state against the code that makes them true,
and the plugin manifests.

## License

MIT. Made by the mails.ai team.
