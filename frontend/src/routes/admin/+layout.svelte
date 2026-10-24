<script lang="ts">
  import { resolve } from "$app/paths";
  import { page } from "$app/state";
  import { onMount, type Snippet } from "svelte";
  import AppShell from "$lib/components/AppShell.svelte";
  import type { Capability } from "$lib/roles";
  import { can, settle, type SessionInfo } from "$lib/session.svelte";

  let { children }: { children: Snippet } = $props();
  let info = $state<SessionInfo | null>(null);

  type Section = "/admin/users" | "/admin/security" | "/admin/server" | "/admin/audit";

  const SECTIONS: { path: Section; label: string; needs: Capability }[] = [
    { path: "/admin/users", label: "Users", needs: "administer" },
    { path: "/admin/security", label: "Security", needs: "administer" },
    { path: "/admin/server", label: "Server", needs: "administer" },
    { path: "/admin/audit", label: "Audit log", needs: "read_audit_log" },
  ];

  const sections = $derived(SECTIONS.filter((s) => can(info, s.needs)));

  onMount(async () => {
    info = await settle("app");
  });
</script>

{#if info}
  <AppShell {info}>
    {#if sections.length}
      <div class="admin">
        <nav class="side" aria-label="Admin">
          {#each sections as section (section.path)}
            <a href={resolve(section.path)}
              aria-current={page.url.pathname.startsWith(section.path) ? "page" : undefined}>
              {section.label}
            </a>
          {/each}
        </nav>
        <div class="main">{@render children()}</div>
      </div>
    {:else}
      <main class="page-content">
        <h1 class="title">Admin</h1>
        <p class="alert alert-warning">You don't have access to the admin panel.</p>
      </main>
    {/if}
  </AppShell>
{/if}

<style>
  .admin {
    display: grid;
    grid-template-columns: 200px minmax(0, 1fr);
    gap: var(--space-6);
    width: 100%;
    max-width: 1280px;
    margin: 0 auto;
    padding: var(--space-8) var(--space-6);
  }
  .side {
    display: flex;
    flex-direction: column;
    gap: var(--space-1);
  }
  .side a {
    padding: 8px 12px;
    border-radius: var(--radius-sm);
    color: var(--text-muted);
    font: var(--type-label);
    text-decoration: none;
  }
  .side a:hover,
  .side a[aria-current="page"] {
    background: var(--surface-subtle);
    color: var(--text);
  }
  .main {
    display: flex;
    flex-direction: column;
    gap: var(--space-6);
    min-width: 0;
  }
  @media (max-width: 800px) {
    .admin {
      grid-template-columns: 1fr;
      padding: var(--space-6) var(--space-4);
    }
    .side {
      flex-direction: row;
      flex-wrap: wrap;
    }
  }
</style>
