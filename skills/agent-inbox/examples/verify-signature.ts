// Verify the signature on a mails.ai webhook delivery.
// Library file: import verifySignature from your webhook handler. Needs only Node's crypto module.
//
// How mails.ai signs a delivery:
//   header   X-Mails-Signature: t=<unix seconds>,v1=<hex digest>
//   digest   HMAC-SHA256(key = signing secret, message = `${t}.${rawBody}`)
// The signing secret is the whole `whsec_...` string, used as UTF-8 text.
// rawBody is the request body exactly as received. Do not parse and re-serialize it first.
// Every v1 in the header is checked, and the delivery passes when any of them matches.
import { createHmac, timingSafeEqual } from "node:crypto";

/** How old a signature may be, in seconds. mails.ai's own verifier uses the same window. */
export const DEFAULT_TOLERANCE_SECONDS = 300;

export function verifySignature(
  rawBody: string,
  signatureHeader: string | null | undefined,
  signingSecret: string,
  toleranceSeconds: number = DEFAULT_TOLERANCE_SECONDS,
  nowSeconds: number = Math.floor(Date.now() / 1000),
): boolean {
  if (!signatureHeader || !signingSecret) return false;

  let t: string | undefined;
  const digests: string[] = [];
  for (const piece of signatureHeader.split(",")) {
    const eq = piece.indexOf("=");
    if (eq < 0) continue;
    const key = piece.slice(0, eq).trim();
    const value = piece.slice(eq + 1).trim();
    if (key === "t" && t === undefined) t = value;
    else if (key === "v1") digests.push(value);
  }
  if (!t || !/^\d{1,15}$/.test(t)) return false;

  // An old timestamp means a captured request is being replayed. A far-future one is not ours.
  const timestamp = Number(t);
  if (Math.abs(nowSeconds - timestamp) > toleranceSeconds) return false;

  const expected = createHmac("sha256", signingSecret).update(`${timestamp}.${rawBody}`).digest();
  return digests.some((digest) => /^[0-9a-fA-F]{64}$/.test(digest) && timingSafeEqual(Buffer.from(digest, "hex"), expected));
}
