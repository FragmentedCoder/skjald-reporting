<script lang="ts">
  import { onMount } from "svelte";
  import { api, ApiError } from "$lib/api";
  import Pill from "$lib/components/Pill.svelte";
  import { dateTime } from "$lib/format";

  interface ServerInfo {
    company_name: string | null;
    address: string;
    version: string;
    schema_version: string | null;
    setup_completed_at: string | null;
    keys: { master_key: boolean; database_key: boolean; backup_key: boolean };
  }

  const KEY_NAMES: [keyof ServerInfo["keys"], string, string][] = [
    ["master_key", "Master key", "Unlocks every other key. In /etc/skjald, never in backups."],
    ["database_key", "Database key", "Opens the encrypted database. Wrapped by the master key."],
    ["backup_key", "Backup key", "Encrypts backups. Wrapped by the master key."],
  ];

  let server = $state<ServerInfo | null>(null);
  let company = $state("");
  let notice = $state<{ tone: "ok" | "critical"; text: string } | null>(null);
  let busy = $state(false);

  function use(info: ServerInfo) {
    server = info;
    company = info.company_name ?? "";
  }

  onMount(async () => {
    try {
      use(await api<ServerInfo>("GET", "/admin/server"));
    } catch (e) {
      notice = { tone: "critical", text: e instanceof ApiError ? e.message : "Not available." };
    }
  });

  async function save(event: SubmitEvent) {
    event.preventDefault();
    busy = true;
    notice = null;
    try {
      use(await api<ServerInfo>("PUT", "/admin/server", { company_name: company }));
      notice = { tone: "ok", text: "Saved." };
    } catch (e) {
      notice = { tone: "critical", text: e instanceof ApiError ? e.message : "Not saved." };
    } finally {
      busy = false;
    }
  }
</script>

<svelte:head><title>Server · Admin · Skjald</title></svelte:head>

<div class="page-header">
  <div>
    <h1 class="title">Server</h1>
    <p class="small muted">This install of Skjald.</p>
  </div>
</div>

{#if notice}
  <p class="alert alert-{notice.tone}" role={notice.tone === "critical" ? "alert" : "status"}>
    {notice.text}
  </p>
{/if}

{#if server}
  <form class="section stack" onsubmit={save}>
    <h2 class="section-title">Company</h2>
    <div class="field form-narrow">
      <label for="company">Company name</label>
      <input id="company" class="input" autocomplete="organization" required bind:value={company} />
      <span class="hint">Shown in the app and on every report.</span>
    </div>
    <div><button class="button button-primary" type="submit" disabled={busy}>Save</button></div>
  </form>

  <section class="section">
    <h2 class="section-title">About this server</h2>
    <dl class="facts">
      <dt>Address</dt>
      <dd class="mono">{server.address}</dd>
      <dt>Version</dt>
      <dd class="mono">{server.version}</dd>
      <dt>Database schema</dt>
      <dd class="mono">{server.schema_version ?? "—"}</dd>
      <dt>Set up</dt>
      <dd>{dateTime(server.setup_completed_at, "Not yet")}</dd>
    </dl>
    <p class="small muted">
      The address is set in <span class="mono">SKJALD_ADDRESS</span> on the server. Passkeys are
      tied to it, so changing it means everyone sets up their passkeys again.
    </p>
  </section>

  <section class="section">
    <h2 class="section-title">Keys</h2>
    <dl class="facts">
      {#each KEY_NAMES as [key, name, about] (key)}
        <dt>{name}</dt>
        <dd>
          <Pill tone={server.keys[key] ? "ok" : "critical"} text={server.keys[key] ? "Present" : "Missing"} />
          <span class="small muted">{about}</span>
        </dd>
      {/each}
    </dl>
  </section>
{/if}
