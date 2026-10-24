<script lang="ts">
  import Download from "@lucide/svelte/icons/download";
  import { onMount } from "svelte";
  import { api, ApiError } from "$lib/api";
  import {
    ACTION_GROUPS,
    describe,
    filterParams,
    type AuditEntry,
    type AuditFilters,
  } from "$lib/audit";
  import Pill from "$lib/components/Pill.svelte";
  import { dateTime } from "$lib/format";

  interface ChainStatus {
    ok: boolean;
    entries_checked: number;
    first_bad_seq: number | null;
    problem: string | null;
  }

  let filters = $state<AuditFilters>({ action: "", actor: "", since: "", until: "" });
  let applied = $state<AuditFilters>({ action: "", actor: "", since: "", until: "" });
  let entries = $state<AuditEntry[]>([]);
  let nextBefore = $state<number | null>(null);
  let actions = $state<string[]>([]);
  let chain = $state<ChainStatus | null>(null);
  let error = $state<string | null>(null);
  let busy = $state(false);

  async function load(more = false) {
    busy = true;
    error = null;
    try {
      const extra: Record<string, string> = more && nextBefore ? { before: String(nextBefore) } : {};
      const page = await api<{ entries: AuditEntry[]; next_before: number | null }>(
        "GET",
        `/audit${filterParams(applied, extra)}`,
      );
      entries = more ? [...entries, ...page.entries] : page.entries;
      nextBefore = page.next_before;
    } catch (e) {
      error = e instanceof ApiError ? e.message : "The audit log could not be loaded.";
    } finally {
      busy = false;
    }
  }

  async function checkChain() {
    chain = null;
    try {
      chain = await api<ChainStatus>("GET", "/audit/verify");
    } catch (e) {
      error = e instanceof ApiError ? e.message : "The chain could not be checked.";
    }
  }

  onMount(async () => {
    await load();
    actions = await api<string[]>("GET", "/audit/actions").catch(() => []);
    await checkChain();
  });

  function apply(event: SubmitEvent) {
    event.preventDefault();
    applied = { ...filters };
    load();
  }

  function clear() {
    filters = { action: "", actor: "", since: "", until: "" };
    applied = { ...filters };
    load();
  }
</script>

<svelte:head><title>Audit log · Admin · Skjald</title></svelte:head>

<div class="page-header">
  <div>
    <h1 class="title">Audit log</h1>
    <p class="small muted">
      Every sign-in, change and export, in a hash chain that shows any edit or removal.
    </p>
  </div>
  <!-- eslint-disable-next-line svelte/no-navigation-without-resolve -- an API download, not a page -->
  <a class="button button-secondary" href="/api/audit/export{filterParams(applied)}" download>
    <Download size={18} aria-hidden="true" />
    Export CSV
  </a>
</div>

<div class="chain">
  {#if chain === null}
    <span class="small muted">Checking the chain…</span>
  {:else if chain.ok}
    <Pill tone="ok" text="Chain intact" />
    <span class="small muted">All {chain.entries_checked} entries check out.</span>
  {:else}
    <Pill tone="critical" text="Chain broken" />
    <span class="small">Entry {chain.first_bad_seq}: {chain.problem}.</span>
  {/if}
  <button class="link-button" type="button" onclick={checkChain}>Check again</button>
</div>

<form class="section filters" onsubmit={apply}>
  <div class="field">
    <label for="action">What</label>
    <select id="action" class="input" bind:value={filters.action}>
      <option value="">Everything</option>
      <optgroup label="Groups">
        {#each ACTION_GROUPS as group (group.value)}
          <option value={group.value}>{group.label}</option>
        {/each}
      </optgroup>
      <optgroup label="Single actions">
        {#each actions as action (action)}<option value={action}>{action}</option>{/each}
      </optgroup>
    </select>
  </div>
  <div class="field">
    <label for="actor">Who</label>
    <input id="actor" class="input" placeholder="Username" autocapitalize="none"
      bind:value={filters.actor} />
  </div>
  <div class="field">
    <label for="since">From</label>
    <input id="since" class="input" type="date" bind:value={filters.since} />
  </div>
  <div class="field">
    <label for="until">To</label>
    <input id="until" class="input" type="date" bind:value={filters.until} />
  </div>
  <div class="button-row filter-buttons">
    <button class="button button-primary" type="submit" disabled={busy}>Show</button>
    <button class="button button-secondary" type="button" onclick={clear}>Clear</button>
  </div>
</form>

{#if error}<p class="alert alert-critical" role="alert">{error}</p>{/if}

<div class="section table-wrap">
  <table class="table">
    <thead>
      <tr><th>#</th><th>When</th><th>Who</th><th>What</th><th>Details</th><th>Address</th></tr>
    </thead>
    <tbody>
      {#each entries as entry (entry.seq)}
        <tr>
          <td class="mono muted">{entry.seq}</td>
          <td class="nowrap">{dateTime(entry.occurred_at)}</td>
          <td>{entry.actor_name ?? "—"}</td>
          <td class="mono">{entry.action}</td>
          <td class="details">{describe(entry.details)}</td>
          <td class="mono">{entry.ip ?? "—"}</td>
        </tr>
      {:else}
        <tr><td colspan="6" class="muted">Nothing matches these filters.</td></tr>
      {/each}
    </tbody>
  </table>
</div>

{#if nextBefore}
  <div>
    <button class="button button-secondary" type="button" disabled={busy} onclick={() => load(true)}>
      Load more
    </button>
  </div>
{/if}

<style>
  .chain {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--space-3);
  }
  .filters {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
    align-items: end;
    gap: var(--space-4);
  }
  .filter-buttons {
    align-self: end;
  }
  .nowrap {
    white-space: nowrap;
  }
  .details {
    max-width: 360px;
    overflow-wrap: anywhere;
  }
</style>
