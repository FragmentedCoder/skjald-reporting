import {
  browserSupportsWebAuthn,
  startAuthentication,
  startRegistration,
  WebAuthnError,
} from "@simplewebauthn/browser";
import { api, ApiError } from "./api";
import type { SecondFactorResult } from "./session.svelte";

export { browserSupportsWebAuthn };

export function passkeyErrorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  if (error instanceof WebAuthnError && error.code === "ERROR_AUTHENTICATOR_PREVIOUSLY_REGISTERED") {
    return "That passkey is already set up for your account.";
  }
  if (error instanceof Error && error.name === "NotAllowedError") {
    return "The passkey prompt was closed or timed out. Try again when you're ready.";
  }
  return "Your browser couldn't use a passkey here. Try again, or choose another way.";
}

export async function registerPasskey(label: string): Promise<SecondFactorResult> {
  const optionsJSON = await api<Parameters<typeof startRegistration>[0]["optionsJSON"]>(
    "POST",
    "/auth/mfa/passkey/registration-options",
  );
  const credential = await startRegistration({ optionsJSON });
  return api<SecondFactorResult>("POST", "/auth/mfa/passkey/register", { credential, label });
}

export async function verifyWithPasskey(): Promise<SecondFactorResult> {
  const optionsJSON = await api<Parameters<typeof startAuthentication>[0]["optionsJSON"]>(
    "POST",
    "/auth/mfa/passkey/authentication-options",
  );
  const credential = await startAuthentication({ optionsJSON });
  return api<SecondFactorResult>("POST", "/auth/mfa/passkey/verify", { credential });
}
