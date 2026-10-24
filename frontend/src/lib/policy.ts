export interface SecuritySettings {
  min_password_length: number;
  breach_check_enabled: boolean;
  lockout_threshold: number;
  lockout_minutes: number;
  idle_timeout_minutes: number;
  max_session_hours: number;
}

export interface AdminSecurity extends SecuritySettings {
  admin_allowlist: string[];
  your_address: string | null;
}

/** Pick only the policy fields, e.g. to send back what the server returned. */
export function securitySettings(values: SecuritySettings): SecuritySettings {
  return {
    min_password_length: values.min_password_length,
    breach_check_enabled: values.breach_check_enabled,
    lockout_threshold: values.lockout_threshold,
    lockout_minutes: values.lockout_minutes,
    idle_timeout_minutes: values.idle_timeout_minutes,
    max_session_hours: values.max_session_hours,
  };
}
