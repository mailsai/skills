// Add your own sending domain, print the DNS records to create, and show which ones are live.
// Run: MAILS_API_KEY=mk_live_... npx tsx custom-domain.ts mail.example.com [--now]
//
// Needs a paid plan and a key with the `manage` scope. Run it again after you add the
// records: it finds the domain it registered before and shows its current state.
import { createClient, MailsError } from "@mailsai/sdk";

const mails = createClient(); // reads MAILS_API_KEY

async function main(): Promise<void> {
  const name = process.argv.slice(2).find((arg) => !arg.startsWith("--"));
  if (!name) throw new Error("usage: custom-domain.ts <domain> [--now]");

  const existing = await mails.domains.list();
  let domain = existing.data.find((d) => d.domain === name.toLowerCase());
  if (!domain) {
    domain = await mails.domains.create(name);
    console.log(`registered ${domain.domain} as ${domain.id}`);
  }

  // mails.ai looks the records up every 15 minutes, so reading the domain shows fresh state.
  // --now asks for a lookup at once. Each one that fails counts, and after 20 failed
  // lookups the domain is marked failed, so do not call it in a loop.
  domain = process.argv.includes("--now")
    ? await mails.domains.verify(domain.id)
    : await mails.domains.get(domain.id);

  console.log(`\nstatus: ${domain.status}${domain.fail_reason ? ` (${domain.fail_reason})` : ""}\n`);
  for (const record of domain.dns_records) {
    const state = record.verified ? "found" : record.required ? "MISSING" : "missing (optional)";
    console.log(`${state.padEnd(18)} ${record.type.padEnd(5)} ${record.host}`);
    console.log(`${"".padEnd(18)} value: ${record.value}`);
    // Follow the instruction when there is one. An SPF value is usually merged into the
    // record you already have: a domain with two SPF records fails SPF.
    if (record.instruction) console.log(`${"".padEnd(18)} note:  ${record.instruction}`);
  }
  if (domain.status !== "verified") {
    console.log("\nCreate the missing records at your DNS host. mails.ai checks again within 15 minutes.");
  }
}

main().catch((error: unknown) => {
  if (error instanceof MailsError && error.code === "feature_not_enabled") {
    console.error(`Custom domains are not available: ${error.message}`);
  } else {
    console.error(error);
  }
  process.exit(1);
});
