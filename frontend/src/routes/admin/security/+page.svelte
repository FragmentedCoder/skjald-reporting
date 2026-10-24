<script lang="ts">
  import { onMount } from "svelte";
  import { api, ApiError } from "$lib/api";
  import PolicyFields from "$lib/components/PolicyFields.svelte";
  import { securitySettings, type AdminSecurity, type SecuritySettings } from "$lib/policy";

  let values = $state<SecuritySettings | null>(null);
  let allowlist = $state("");
  let yourAddress = $state<string | null>(null);
  let notice = $state<{ tone: "ok" | "critical"; text: string } | null>(null);
  let busy = $state(false);

  function use(security: AdminSecurity) {
    values = securitySettings(security);
    allowlist = security.admin_allowlist.join("\n");
    yourAddress = security.your_address;
  }

  onMount(async () => {
    try {
      use(await api<AdminSecurity>("GET", "/admin/security"));
    } catch (e) {
      notice = { tone: "critical", text: e instanceof ApiError ? e.message : "Not available." };
    }
  });

  async function save(event: SubmitEvent) {
    event.preventDefault();
    if (!values) return;
    busy = true;
    notice = null;
    try {
      use(await api<AdminSecurity>("PUT", "/admin/security", {
        ...values,
        admin_allowlist: allowlist.split(/\s+/).filter(Boolean),
      }));
      notice = { tone: "ok", text: "Saved. The new settings apply from the next sign-in." };
    } catch (e) {
      notice = {
        tone: "critical",
        text: e instanceof ApiError ? e.message : "The settings could not be saved.",
      };
    } finally {
      busy = false;
    }
  }
</script>

<svelte:head><title>Security · Admin · Skjald</title></svelte:head>

<div class="page-header">
  <div>
    <h1 class="title">Security</h1>
    <p class="small muted">Passwords, lockout, sessions, and where the admin panel answers from.</p>
  </div>
</div>

{#if notice}
  <p class="alert alert-{notice.tone}" role={notice.tone === "critical" ? "alert" : "status"}>
    {notice.text}
  </p>
{/if}

{#if values}
  <form class="stack" onsubmit={save}>
    <section class="section">
      <h2 class="section-title">Passwords, lockout and sessions</h2>
      <div class="stack form-narrow">
        <PolicyFields bind:values />
      </div>
    </section>

    <section class="section">
      <h2 class="section-title">Admin panel allowlist</h2>
      <p class="small muted">
        Addresses or ranges the admin panel answers from, one per line, such as 10.20.0.0/24.
        Leave it empty to allow every address on your network. If it ever locks everyone out,
        run <span class="mono">docker compose exec app python -m app.console reset-allowlist</span>
        on the server.
      </p>
      <div class="field form-narrow">
        <label for="allowlist">Allowed addresses</label>
        <textarea id="allowlist" class="input mono" rows="4" spellcheck="false"
          aria-describedby="allowlist-hint" bind:value={allowlist}></textarea>
        <span class="hint" id="allowlist-hint">
          Your address right now: <span class="mono">{yourAddress ?? "unknown"}</span>. Skjald
          won't save a list that leaves it out.
        </span>
      </div>
    </section>

    <div><button class="button button-primary" type="submit" disabled={busy}>Save settings</button></div>
  </form>
{/if}
