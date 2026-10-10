"""Add your own sending domain, print the DNS records to create, and show which ones are live.

Run: MAILS_API_KEY=mk_live_... python3 custom_domain.py mail.example.com [--now]

Needs a paid plan and a key with the `manage` scope. Run it again after you add the
records: it finds the domain it registered before and shows its current state.
"""
from __future__ import annotations

import sys

from mailsai import Client, MailsError


def main() -> None:
    names = [arg for arg in sys.argv[1:] if not arg.startswith("--")]
    if not names:
        sys.exit("usage: custom_domain.py <domain> [--now]")
    name = names[0].lower()
    client = Client()  # reads MAILS_API_KEY

    existing = client.list_domains()
    domain = next((d for d in existing["data"] if d["domain"] == name), None)
    if domain is None:
        domain = client.create_domain(name)
        print(f"registered {domain['domain']} as {domain['id']}")

    # mails.ai looks the records up every 15 minutes, so reading the domain shows fresh state.
    # --now asks for a lookup at once. Each one that fails counts, and after 20 failed
    # lookups the domain is marked failed, so do not call it in a loop.
    if "--now" in sys.argv[1:]:
        domain = client.verify_domain(domain["id"])
    else:
        domain = client.get_domain(domain["id"])

    reason = f" ({domain['fail_reason']})" if domain.get("fail_reason") else ""
    print(f"\nstatus: {domain['status']}{reason}\n")
    for record in domain["dns_records"]:
        if record["verified"]:
            state = "found"
        else:
            state = "MISSING" if record["required"] else "missing (optional)"
        print(f"{state:<18} {record['type']:<5} {record['host']}")
        print(f"{'':<18} value: {record['value']}")
        # Follow the instruction when there is one. An SPF value is usually merged into the
        # record you already have: a domain with two SPF records fails SPF.
        if record.get("instruction"):
            print(f"{'':<18} note:  {record['instruction']}")
    if domain["status"] != "verified":
        print("\nCreate the missing records at your DNS host. mails.ai checks again within 15 minutes.")


if __name__ == "__main__":
    try:
        main()
    except MailsError as error:
        if error.code == "feature_not_enabled":
            sys.exit(f"Custom domains are not available: {error.message}")
        raise
