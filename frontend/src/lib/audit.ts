export interface AuditEntry {
  seq: number;
  occurred_at: string;
  actor_name: string | null;
  action: string;
  target_type: string | null;
  target_id: string | null;
  ip: string | null;
  details: Record<string, unknown>;
}

export interface AuditFilters {
  action: string;
  actor: string;
  since: string;
  until: string;
}

export const ACTION_GROUPS: { value: string; label: string }[] = [
  { value: "auth.*", label: "Sign-in and security" },
  { value: "admin.*", label: "Administration" },
  { value: "account.*", label: "Account changes" },
  { value: "setup.*", label: "Setup" },
  { value: "audit.*", label: "Audit log" },
];

/** The filters as query parameters, leaving out the empty ones. */
export function filterParams(filters: AuditFilters, extra: Record<string, string> = {}): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries({ ...filters, ...extra })) {
    if (value) params.set(key, value);
  }
  const query = params.toString();
  return query ? `?${query}` : "";
}

/** Details as short "key: value" text for a table cell. */
export function describe(details: Record<string, unknown>): string {
  return Object.entries(details)
    .map(([key, value]) => `${key.replaceAll("_", " ")}: ${
      typeof value === "object" ? JSON.stringify(value) : String(value)
    }`)
    .join(" · ");
}
