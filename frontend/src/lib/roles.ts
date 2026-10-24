// Mirrors backend/app/roles.py. What a role *allows* always comes from the server
// (SessionInfo.user.capabilities); this file only names things for people.

export type Role = "administrator" | "report_designer" | "technician" | "reviewer" | "auditor";

export type Capability =
  | "manage_customers"
  | "create_projects_and_reports"
  | "fill_in_reports"
  | "review_and_countersign"
  | "build_templates"
  | "edit_library"
  | "lock_library_entries"
  | "check_signed_reports"
  | "edit_styles"
  | "administer"
  | "break_checkouts"
  | "read_audit_log";

export const ROLES: { role: Role; name: string; description: string }[] = [
  {
    role: "administrator",
    name: "Administrator",
    description: "Everything: all customers, users, security, keys and settings.",
  },
  {
    role: "report_designer",
    name: "Report designer",
    description: "Builds templates, custom fields and styles.",
  },
  {
    role: "technician",
    name: "Technician",
    description: "Writes reports for the customers they are assigned to.",
  },
  {
    role: "reviewer",
    name: "Reviewer",
    description: "Reviews and countersigns reports for assigned customers.",
  },
  { role: "auditor", name: "Auditor", description: "Reads the audit log and report metadata." },
];

export function roleName(role: Role): string {
  return ROLES.find((r) => r.role === role)?.name ?? role;
}
