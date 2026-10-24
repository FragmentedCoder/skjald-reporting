<script lang="ts">
  import { onMount } from "svelte";
  import AppShell from "$lib/components/AppShell.svelte";
  import { roleName } from "$lib/roles";
  import { settle, type SessionInfo } from "$lib/session.svelte";

  let info = $state<SessionInfo | null>(null);

  onMount(async () => {
    info = await settle("app");
  });
</script>

<svelte:head><title>Skjald</title></svelte:head>

{#if info}
  <AppShell {info}>
    <main class="page-content">
      <div class="heading">
        <h1 class="title">Welcome, {info.user.display_name}</h1>
        {#if info.user.roles.length}
          <p class="small muted">{info.user.roles.map(roleName).join(", ")}</p>
        {/if}
      </div>
      <section class="empty">
        <p>The hall is quiet for now.</p>
        <p class="small muted">Customers, projects and reports will appear here.</p>
      </section>
    </main>
  </AppShell>
{/if}

<style>
  .heading {
    display: flex;
    flex-direction: column;
    gap: var(--space-1);
  }
  .empty {
    display: flex;
    flex-direction: column;
    gap: var(--space-1);
    padding: var(--space-8);
    border: 1px dashed var(--border-strong);
    border-radius: var(--radius-lg);
    text-align: center;
  }
</style>
