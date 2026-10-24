<script lang="ts">
  import { resolve } from "$app/paths";
  import { page } from "$app/state";
  import LogOut from "@lucide/svelte/icons/log-out";
  import type { Snippet } from "svelte";
  import Mark from "./Mark.svelte";
  import { can, signOut, type SessionInfo } from "$lib/session.svelte";

  let { info, children }: { info: SessionInfo; children: Snippet } = $props();

  const showAdmin = $derived(can(info, "administer") || can(info, "read_audit_log"));
  const path = $derived(page.url.pathname);
</script>

<header class="bar">
  <a class="brand" href={resolve("/")}>
    <Mark size={32} />
    <span class="wordmark">Skjald</span>
  </a>
  <nav class="nav" aria-label="Main">
    <a href={resolve("/")} aria-current={path === "/" ? "page" : undefined}>Home</a>
    {#if showAdmin}
      <a href={resolve("/admin")} aria-current={path.startsWith("/admin") ? "page" : undefined}>
        Admin
      </a>
    {/if}
    <a href={resolve("/account")} aria-current={path === "/account" ? "page" : undefined}>
      Your account
    </a>
  </nav>
  <div class="who">
    <span class="small muted">{info.user.display_name}</span>
    <button class="button button-secondary" type="button" onclick={signOut}>
      <LogOut size={16} aria-hidden="true" />
      Sign out
    </button>
  </div>
</header>

{@render children()}

<style>
  .bar {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--space-3) var(--space-6);
    padding: var(--space-3) var(--space-6);
    border-bottom: 1px solid var(--border);
    background: var(--surface);
  }
  .brand {
    display: flex;
    align-items: center;
    gap: var(--space-3);
    color: var(--text);
    text-decoration: none;
  }
  .wordmark {
    font: var(--type-subheading);
  }
  .nav {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-1);
    flex: 1;
  }
  .nav a {
    padding: 6px 12px;
    border-radius: var(--radius-sm);
    color: var(--text-muted);
    font: var(--type-label);
    text-decoration: none;
  }
  .nav a:hover {
    background: var(--surface-subtle);
    color: var(--text);
  }
  .nav a[aria-current="page"] {
    background: var(--surface-subtle);
    color: var(--text);
  }
  .who {
    display: flex;
    align-items: center;
    gap: var(--space-3);
  }
  @media (max-width: 640px) {
    .bar {
      padding-inline: var(--space-4);
    }
    .nav {
      order: 3;
      flex-basis: 100%;
    }
  }
</style>
