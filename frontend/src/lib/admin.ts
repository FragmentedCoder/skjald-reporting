import type { Role } from "./roles";

export interface UserSummary {
  id: number;
  username: string;
  display_name: string;
  email: string | null;
  roles: Role[];
  is_active: boolean;
  is_break_glass: boolean;
  locked: boolean;
  second_factors: number;
  password_change_required: boolean;
  last_sign_in_at: string | null;
  created_at: string;
}

export interface UserDetail extends UserSummary {
  password_expires_at: string | null;
  factors: {
    id: number;
    kind: "totp" | "webauthn";
    label: string;
    created_at: string;
    last_used_at: string | null;
  }[];
  recovery_codes_left: number;
  sessions: {
    id: number;
    created_at: string;
    last_seen_at: string;
    ip: string | null;
    user_agent: string | null;
    second_factor_done: boolean;
  }[];
}

export interface TemporaryPassword {
  user: UserDetail;
  temporary_password: string;
  expires_at: string;
}

type Tone = "ok" | "warning" | "critical" | "info" | "neutral";

/** The one status that matters most, as a word and a tone. */
export function userStatus(user: UserSummary): { tone: Tone; text: string } {
  if (!user.is_active) return { tone: "neutral", text: "Disabled" };
  if (user.locked) return { tone: "critical", text: "Locked" };
  if (user.password_change_required) return { tone: "warning", text: "Awaiting first sign-in" };
  if (user.second_factors === 0) return { tone: "warning", text: "No second factor" };
  return { tone: "ok", text: "Active" };
}
