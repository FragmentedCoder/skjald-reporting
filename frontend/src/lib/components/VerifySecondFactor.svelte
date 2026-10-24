<script lang="ts">
  import KeyRound from "@lucide/svelte/icons/key-round";
  import { api, ApiError } from "$lib/api";
  import { passkeyErrorMessage, verifyWithPasskey } from "$lib/passkeys";
  import { sessionEnded, type SecondFactorResult, type SessionInfo } from "$lib/session.svelte";

  let {
    info,
    onDone,
  }: { info: SessionInfo; onDone: (result: SecondFactorResult) => void } = $props();

  let useRecovery = $state(false);
  let code = $state("");
  let recoveryCode = $state("");
  let error = $state<string | null>(null);
  let busy = $state(false);

  const hasPasskey = $derived(info.methods.includes("webauthn"));
  const hasApp = $derived(info.methods.includes("totp"));
  const hasRecovery = $derived(info.methods.includes("recovery_code"));

  async function finish(attempt: () => Promise<SecondFactorResult>) {
    busy = true;
    error = null;
    try {
      onDone(await attempt());
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) {
        await sessionEnded(e.message);
        return;
      }
      error = e instanceof ApiError ? e.message : passkeyErrorMessage(e);
    } finally {
      busy = false;
    }
  }

  function submitCode(event: SubmitEvent) {
    event.preventDefault();
    finish(() => api("POST", "/auth/mfa/totp/verify", { code }));
    code = "";
  }

  function submitRecovery(event: SubmitEvent) {
    event.preventDefault();
    finish(() => api("POST", "/auth/mfa/recovery-code/verify", { code: recoveryCode }));
    recoveryCode = "";
  }
</script>

{#if error}<p class="alert alert-critical" role="alert">{error}</p>{/if}

{#if useRecovery}
  <form class="stack" onsubmit={submitRecovery}>
    <div class="field">
      <label for="recovery-code">Recovery code</label>
      <input
        id="recovery-code"
        class="input code"
        autocomplete="off"
        autocapitalize="none"
        spellcheck="false"
        required
        bind:value={recoveryCode}
      />
      <span class="hint">Each recovery code works once.</span>
    </div>
    <button class="button button-primary button-block" type="submit" disabled={busy}>
      Use recovery code
    </button>
  </form>
  <button class="link-button" type="button" onclick={() => (useRecovery = false)}>
    Use another way
  </button>
{:else}
  {#if hasPasskey}
    <button
      class="button button-primary button-block"
      type="button"
      disabled={busy}
      onclick={() => finish(verifyWithPasskey)}
    >
      <KeyRound size={18} aria-hidden="true" />
      Use passkey or security key
    </button>
  {/if}

  {#if hasPasskey && hasApp}<p class="or muted small">or</p>{/if}

  {#if hasApp}
    <form class="stack" onsubmit={submitCode}>
      <div class="field">
        <label for="code">Code from your authenticator app</label>
        <input
          id="code"
          class="input code"
          inputmode="numeric"
          autocomplete="one-time-code"
          maxlength="7"
          required
          bind:value={code}
        />
      </div>
      <button
        class="button button-block {hasPasskey ? 'button-secondary' : 'button-primary'}"
        type="submit"
        disabled={busy}
      >
        Verify code
      </button>
    </form>
  {/if}

  {#if hasRecovery}
    <button class="link-button" type="button" onclick={() => (useRecovery = true)}>
      Use a recovery code instead
    </button>
  {/if}
{/if}

<style>
  .or {
    text-align: center;
  }
</style>
