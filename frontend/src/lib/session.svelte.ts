import { goto } from "$app/navigation";
import { resolve } from "$app/paths";
import { api, ApiError, setCsrfToken } from "./api";
import type { Capability, Role } from "./roles";

export type Method = "totp" | "webauthn" | "recovery_code";
export type Theme = "system" | "light" | "dark";

export interface SessionInfo {
  user: {
    id: number;
    username: string;
    display_name: string;
    theme: Theme;
    roles: Role[];
    capabilities: Capability[];
  };
  second_factor: "enrol" | "verify" | "done";
  methods: Method[];
  password_change_required: boolean;
  csrf_token: string;
  expires_at: string;
}

export interface SecondFactorResult {
  session: SessionInfo;
  recovery_codes: string[] | null;
}

export const session = $state<{
  current: SessionInfo | null;
  loaded: boolean;
  // A message for the sign-in page, such as why the session ended.
  notice: string | null;
  // A fresh install: every page leads to the setup wizard until it is finished.
  setupNeeded: boolean;
}>({ current: null, loaded: false, notice: null, setupNeeded: false });

/** Light or dark as the user chose; "system" leaves it to the browser's setting. */
export function applyTheme(theme: Theme | undefined): void {
  if (typeof document === "undefined") return;
  if (theme === "light" || theme === "dark") document.documentElement.dataset.theme = theme;
  else delete document.documentElement.dataset.theme;
}

export function useSession(info: SessionInfo | null): void {
  session.current = info;
  setCsrfToken(info?.csrf_token ?? null);
  applyTheme(info?.user.theme);
}

export async function loadSession(): Promise<SessionInfo | null> {
  try {
    session.setupNeeded = (await api<{ needed: boolean }>("GET", "/setup/status")).needed;
    useSession(await api<SessionInfo>("GET", "/auth/session"));
  } catch (error) {
    if (!(error instanceof ApiError && error.status === 401)) throw error;
    useSession(null);
  } finally {
    session.loaded = true;
  }
  return session.current;
}

export type Place =
  | "/"
  | "/setup"
  | "/sign-in"
  | "/sign-in/set-up"
  | "/sign-in/verify"
  | "/sign-in/new-password";

/**
 * The page a session belongs on. A second factor already set up comes before a
 * new password; setting one up comes after it.
 */
export function placeFor(info: SessionInfo | null, setupNeeded = session.setupNeeded): Place {
  if (setupNeeded) return "/setup";
  if (!info) return "/sign-in";
  if (info.second_factor === "verify") return "/sign-in/verify";
  if (info.password_change_required) return "/sign-in/new-password";
  if (info.second_factor === "enrol") return "/sign-in/set-up";
  return "/";
}

/**
 * Load the session if needed, and move on if this page isn't where it belongs.
 * "app" means any page for someone fully signed in. Returns the session when the
 * page may show (null when it moved on, or for pages for people not signed in).
 */
export async function settle(here: Place | "app"): Promise<SessionInfo | null> {
  const info = session.loaded ? session.current : await loadSession();
  const place = placeFor(info);
  const belongs = here === "app" ? place === "/" : place === here;
  if (!belongs) await goto(resolve(place), { replaceState: true });
  return belongs ? info : null;
}

export function can(info: SessionInfo | null, capability: Capability): boolean {
  return info?.user.capabilities.includes(capability) ?? false;
}

/** The server ended the session (signed out elsewhere, timed out, locked). */
export async function sessionEnded(message: string): Promise<void> {
  useSession(null);
  session.notice = message;
  await goto(resolve(placeFor(null)), { replaceState: true });
}

export async function signOut(): Promise<void> {
  try {
    await api("POST", "/auth/sign-out");
  } catch {
    // Signed out on the server already, or unreachable: forget the session either way.
  }
  useSession(null);
  await goto(resolve(placeFor(null)), { replaceState: true });
}
