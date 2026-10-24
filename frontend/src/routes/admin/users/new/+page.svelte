<script lang="ts">
  import { resolve } from "$app/paths";
  import { api, ApiError } from "$lib/api";
  import type { TemporaryPassword } from "$lib/admin";
  import TemporaryPasswordNotice from "$lib/components/TemporaryPasswordNotice.svelte";
  import { ROLES, type Role } from "$lib/roles";

  let form = $state({ display_name: "", username: "", email: "", roles: [] as Role[] });
  let created = $state<TemporaryPassword | null>(null);
  let error = $state<string | null>(null);
  let busy = $state(false);

  async function submit(event: SubmitEvent) {
    event.preventDefault();
    busy = true;
    error = null;
    try {
      created = await api<TemporaryPassword>("POST", "/admin/users", {
        display_name: form.display_name,
        username: form.username,
        email: form.email || null,
        roles: form.roles,
      });
    } catch (e) {
      error = e instanceof ApiError ? e.message : "The user could not be added.";
    } finally {
      busy = false;
    }
  }
</script>

<svelte:head><title>Add user · Admin · Skjald</title></svelte:head>

<div class="page-header">
  <div>
    <a class="small" href={resolve("/admin/users")}>Users</a>
    <h1 class="title">Add user</h1>
  </div>
</div>

{#if created}
  <section class="section">
    <h2 class="section-title">{created.user.display_name} is added</h2>
    <TemporaryPasswordNotice name={created.user.display_name}
      password={created.temporary_password} expiresAt={created.expires_at} />
    <div class="button-row">
      <a class="button button-primary"
        href={resolve("/admin/users/[id]", { id: String(created.user.id) })}>Open user</a>
      <a class="button button-secondary" href={resolve("/admin/users")}>Back to users</a>
    </div>
  </section>
{:else}
  <form class="section stack form-wide" onsubmit={submit}>
    {#if error}<p class="alert alert-critical" role="alert">{error}</p>{/if}
    <div class="field">
      <label for="display-name">Full name</label>
      <input id="display-name" class="input" required bind:value={form.display_name} />
    </div>
    <div class="field">
      <label for="username">Username</label>
      <input id="username" class="input" autocapitalize="none" spellcheck="false" required
        aria-describedby="username-hint" bind:value={form.username} />
      <span class="hint" id="username-hint">What they sign in with. No spaces.</span>
    </div>
    <div class="field">
      <label for="email">Email (optional)</label>
      <input id="email" class="input" type="email" bind:value={form.email} />
    </div>
    <fieldset class="checks roles">
      <legend class="check-title">Roles</legend>
      {#each ROLES as option (option.role)}
        <label class="check">
          <input type="checkbox" value={option.role} bind:group={form.roles} />
          <span>
            <span class="check-title">{option.name}</span>
            <span class="small muted">{option.description}</span>
          </span>
        </label>
      {/each}
    </fieldset>
    <p class="small muted">
      Skjald makes a temporary password for them. They replace it and set up a second factor
      the first time they sign in.
    </p>
    <div class="button-row">
      <button class="button button-primary" type="submit" disabled={busy}>Add user</button>
      <a class="button button-secondary" href={resolve("/admin/users")}>Cancel</a>
    </div>
  </form>
{/if}

<style>
  .form-wide {
    max-width: 640px;
  }
  .roles {
    margin: 0;
    padding: 0;
    border: 0;
  }
  .roles legend {
    margin-bottom: var(--space-2);
  }
</style>
