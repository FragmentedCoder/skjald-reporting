<script lang="ts">
  import { goto } from "$app/navigation";
  import { resolve } from "$app/paths";
  import { onMount } from "svelte";
  import { api, ApiError } from "$lib/api";
  import AuthLayout from "$lib/components/AuthLayout.svelte";
  import {
    placeFor,
    sessionEnded,
    settle,
    signOut,
    useSession,
    type SessionInfo,
  } from "$lib/session.svelte";

  let info = $state<SessionInfo | null>(null);
  let password = $state("");
  let repeat = $state("");
  let error = $state<string | null>(null);
  let busy = $state(false);

  onMount(async () => {
    info = await settle("/sign-in/new-password");
  });

  async function submit(event: SubmitEvent) {
    event.preventDefault();
    if (password !== repeat) {
      error = "The two passwords don't match.";
      return;
    }
    busy = true;
    error = null;
    try {
      const next = await api<SessionInfo>("POST", "/auth/new-password", { new_password: password });
      useSession(next);
      await goto(resolve(placeFor(next)));
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) {
        await sessionEnded(e.message);
        return;
      }
      error = e instanceof ApiError ? e.message : "Something went wrong. Try again.";
    } finally {
      password = repeat = "";
      busy = false;
    }
  }
</script>

<svelte:head><title>Choose your password · Skjald</title></svelte:head>

{#if info}
  <AuthLayout
    heading="Choose your password"
    intro="You signed in with a temporary password from an administrator. Choose your own to continue."
  >
    <form class="stack" onsubmit={submit}>
      {#if error}<p class="alert alert-critical" role="alert">{error}</p>{/if}
      <input type="text" class="visually-hidden" autocomplete="username" value={info.user.username}
        readonly tabindex="-1" aria-hidden="true" />
      <div class="field">
        <label for="new-password">New password</label>
        <input
          id="new-password"
          class="input"
          type="password"
          autocomplete="new-password"
          aria-describedby="new-password-hint"
          required
          bind:value={password}
        />
        <span class="hint" id="new-password-hint">
          A few random words work well. It can't contain your username.
        </span>
      </div>
      <div class="field">
        <label for="repeat-password">Repeat password</label>
        <input
          id="repeat-password"
          class="input"
          type="password"
          autocomplete="new-password"
          required
          bind:value={repeat}
        />
      </div>
      <button class="button button-primary button-block" type="submit" disabled={busy}>
        Save password
      </button>
    </form>
    {#snippet footer()}
      <button class="link-button" type="button" onclick={signOut}>Sign out</button>
    {/snippet}
  </AuthLayout>
{/if}
