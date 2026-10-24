<script lang="ts">
  import { goto } from "$app/navigation";
  import { resolve } from "$app/paths";
  import { onMount } from "svelte";
  import AuthLayout from "$lib/components/AuthLayout.svelte";
  import VerifySecondFactor from "$lib/components/VerifySecondFactor.svelte";
  import {
    settle,
    signOut,
    useSession,
    type SecondFactorResult,
    type SessionInfo,
  } from "$lib/session.svelte";

  let info = $state<SessionInfo | null>(null);

  onMount(async () => {
    info = await settle("/sign-in/verify");
  });

  async function done(result: SecondFactorResult) {
    useSession(result.session);
    await goto(resolve("/"));
  }
</script>

<svelte:head><title>Confirm it's you · Skjald</title></svelte:head>

{#if info}
  <AuthLayout
    heading="Confirm it's you"
    intro={`Signed in as ${info.user.display_name}. Finish with your second step.`}
  >
    <VerifySecondFactor {info} onDone={done} />
    {#snippet footer()}
      <button class="link-button" type="button" onclick={signOut}>Sign out</button>
    {/snippet}
  </AuthLayout>
{/if}
