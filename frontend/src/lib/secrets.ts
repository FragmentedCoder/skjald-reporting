/** Text files for secrets shown once: what the Copy and Download buttons hand over. */

export function recoveryCodesText(username: string, codes: string[]): string {
  return [
    "Skjald recovery codes",
    `For ${username}. Each code lets you sign in once if you lose your second factor.`,
    "",
    ...codes,
    "",
  ].join("\n");
}

export interface RecoveryKit {
  master_key: string;
  backup_key: string;
  address: string;
  company_name: string | null;
  shown_at: string;
}

export function recoveryKitText(kit: RecoveryKit): string {
  return [
    "Skjald recovery kit",
    `${kit.company_name ?? "Skjald"} · ${kit.address} · created ${kit.shown_at.slice(0, 10)}`,
    "",
    "Keep this offline or in your password manager, never on the Skjald server.",
    "Without both keys, no backup of this server can be restored.",
    "",
    `Master key: ${kit.master_key}`,
    `Backup key: ${kit.backup_key}`,
    "",
  ].join("\n");
}
