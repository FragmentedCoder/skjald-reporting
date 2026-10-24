import { encode } from "uqr";

export const QUIET_ZONE = 4;

/**
 * A QR code as one SVG path: a square per dark module. Rendering it ourselves
 * keeps the markup in Svelte, with no {@html} and no inline styles for the CSP.
 */
export function qrPath(text: string): { size: number; d: string } {
  const { data, size } = encode(text, { ecc: "M", border: 0 });
  const parts: string[] = [];
  data.forEach((row, y) =>
    row.forEach((dark, x) => {
      if (dark) parts.push(`M${x + QUIET_ZONE} ${y + QUIET_ZONE}h1v1h-1z`);
    }),
  );
  return { size: size + 2 * QUIET_ZONE, d: parts.join("") };
}

/** Groups a TOTP secret in fours, so it can be typed in by hand. */
export function groupSecret(secret: string): string {
  return secret.match(/.{1,4}/g)?.join(" ") ?? secret;
}
