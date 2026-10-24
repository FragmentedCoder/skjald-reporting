<script lang="ts">
  import { goto } from "$app/navigation";
  import { resolve } from "$app/paths";
  import { onMount } from "svelte";
  import { api, ApiError } from "$lib/api";
  import AuthLayout from "$lib/components/AuthLayout.svelte";
  import { placeFor, session, settle, useSession, type SessionInfo } from "$lib/session.svelte";

  let username = $state("");
  let password = $state("");
  let error = $state<string | null>(null);
  let busy = $state(false);

  onMount(() => {
    error = session.notice;
    session.notice = null;
    settle("/sign-in");
  });

  async function submit(event: SubmitEvent) {
    event.preventDefault();
    busy = true;
    error = null;
    try {
      const info = await api<SessionInfo>("POST", "/auth/sign-in", { username, password });
      useSession(info);
      await goto(resolve(placeFor(info)));
    } catch (e) {
      error = e instanceof ApiError ? e.message : "Something went wrong. Try again.";
    } finally {
      password = "";
      busy = false;
    }
  }
</script>

<svelte:head><title>Sign in · Skjald</title></svelte:head>

<AuthLayout heading="Sign in">
  <form class="stack" onsubmit={submit}>
    {#if error}<p class="alert alert-critical" role="alert">{error}</p>{/if}
    <div class="field">
      <label for="username">Username</label>
      <input
        id="username"
        class="input"
        name="username"
        autocomplete="username"
        autocapitalize="none"
        spellcheck="false"
        required
        bind:value={username}
      />
    </div>
    <div class="field">
      <label for="password">Password</label>
      <input
        id="password"
        class="input"
        type="password"
        name="password"
        autocomplete="current-password"
        required
        bind:value={password}
      />
    </div>
    <button class="button button-primary button-block" type="submit" disabled={busy}>
      {busy ? "Signing in…" : "Sign in"}
    </button>
  </form>
</AuthLayout>
