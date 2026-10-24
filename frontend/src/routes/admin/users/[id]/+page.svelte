<script lang="ts">
  import { resolve } from "$app/paths";
  import { page } from "$app/state";
  import { onMount } from "svelte";
  import { api, ApiError } from "$lib/api";
  import { userStatus, type TemporaryPassword, type UserDetail } from "$lib/admin";
  import Dialog from "$lib/components/Dialog.svelte";
  import Pill from "$lib/components/Pill.svelte";
  import TemporaryPasswordNotice from "$lib/components/TemporaryPasswordNotice.svelte";
  import { browserName, date, dateTime } from "$lib/format";
  import { ROLES, type Role } from "$lib/roles";
  import { session } from "$lib/session.svelte";

  const KIND_NAMES = { totp: "Authenticator app", webauthn: "Passkey or security key" };

  interface Action {
    title: string;
    explain: string;
    confirm: string;
    path: string;
  }

  let user = $state<UserDetail | null>(null);
  let form = $state({ display_name: "", email: "", is_active: true, roles: [] as Role[] });
  let notice = $state<{ tone: "ok" | "critical"; text: string } | null>(null);
  let busy = $state(false);
  let pending = $state<Action | null>(null);
  let confirmOpen = $state(false);
  let temporary = $state<TemporaryPassword | null>(null);
  let temporaryOpen = $state(false);

  const id = $derived(page.params.id);
  const isSelf = $derived(user?.id === session.current?.user.id);
  const status = $derived(user ? userStatus(user) : null);

  function use(detail: UserDetail) {
    user = detail;
    form = {
      display_name: detail.display_name,
      email: detail.email ?? "",
      is_active: detail.is_active,
      roles: [...detail.roles],
    };
  }

  onMount(async () => {
    try {
      use(await api<UserDetail>("GET", `/admin/users/${id}`));
    } catch (e) {
      notice = { tone: "critical", text: e instanceof ApiError ? e.message : "Not found." };
    }
  });

  async function run(action: () => Promise<void>) {
    busy = true;
    notice = null;
    try {
      await action();
    } catch (e) {
      notice = {
        tone: "critical",
        text: e instanceof ApiError ? e.message : "Something went wrong. Try again.",
      };
    } finally {
      busy = false;
    }
  }

  function save(event: SubmitEvent) {
    event.preventDefault();
    run(async () => {
      use(await api<UserDetail>("PATCH", `/admin/users/${id}`, {
        display_name: form.display_name,
        email: form.email,
        is_active: form.is_active,
        roles: form.roles,
      }));
      notice = { tone: "ok", text: "Saved." };
    });
  }

  function ask(action: Action) {
    pending = action;
    confirmOpen = true;
  }

  function confirmed() {
    const action = pending;
    confirmOpen = false;
    if (!action) return;
    run(async () => {
      if (action.path === "reset-password") {
        temporary = await api<TemporaryPassword>("POST", `/admin/users/${id}/reset-password`);
        use(temporary.user);
        temporaryOpen = true;
      } else {
        use(await api<UserDetail>("POST", `/admin/users/${id}/${action.path}`));
        notice = { tone: "ok", text: `${action.title}: done.` };
      }
    });
  }

  function unlock() {
    run(async () => {
      use(await api<UserDetail>("POST", `/admin/users/${id}/unlock`));
      notice = { tone: "ok", text: "Unlocked." };
    });
  }
</script>

<svelte:head><title>{user?.display_name ?? "User"} · Admin · Skjald</title></svelte:head>

<div class="page-header">
  <div>
    <a class="small" href={resolve("/admin/users")}>Users</a>
    <h1 class="title">{user?.display_name ?? "User"}</h1>
    {#if user && status}
      <div class="tags">
        <span class="small muted mono">{user.username}</span>
        <Pill tone={status.tone} text={status.text} />
        {#if user.is_break_glass}<Pill tone="info" text="Break-glass" />{/if}
      </div>
    {/if}
  </div>
</div>

{#if notice}
  <p class="alert alert-{notice.tone}" role={notice.tone === "critical" ? "alert" : "status"}>
    {notice.text}
  </p>
{/if}

{#if user}
  {#if user.is_break_glass}
    <p class="alert alert-warning">
      The break-glass administrator is for setup and emergencies. It always keeps the
      Administrator role and stays active, and every sign-in with it is flagged in the audit log.
    </p>
  {/if}

  <form class="section stack" onsubmit={save}>
    <h2 class="section-title">Details and roles</h2>
    <div class="columns">
      <div class="stack">
        <div class="field">
          <label for="display-name">Full name</label>
          <input id="display-name" class="input" required bind:value={form.display_name} />
        </div>
        <div class="field">
          <label for="email">Email</label>
          <input id="email" class="input" type="email" bind:value={form.email} />
        </div>
        <label class="check">
          <input type="checkbox" bind:checked={form.is_active}
            disabled={isSelf || user.is_break_glass} />
          <span>
            <span class="check-title">Account active</span>
            <span class="small muted">A disabled account can't sign in; its sessions end.</span>
          </span>
        </label>
      </div>
      <fieldset class="checks roles">
        <legend class="check-title">Roles</legend>
        {#each ROLES as option (option.role)}
          <label class="check">
            <input type="checkbox" value={option.role} bind:group={form.roles}
              disabled={option.role === "administrator" && (isSelf || user.is_break_glass)} />
            <span>
              <span class="check-title">{option.name}</span>
              <span class="small muted">{option.description}</span>
            </span>
          </label>
        {/each}
      </fieldset>
    </div>
    <div><button class="button button-primary" type="submit" disabled={busy}>Save changes</button></div>
  </form>

  <section class="section">
    <h2 class="section-title">Sign-in</h2>
    <dl class="facts">
      <dt>Last sign-in</dt>
      <dd>{dateTime(user.last_sign_in_at)}</dd>
      <dt>Password</dt>
      <dd>
        {#if user.password_change_required}
          Temporary, works until {dateTime(user.password_expires_at)}
        {:else}
          Their own
        {/if}
      </dd>
      <dt>Recovery codes</dt>
      <dd>{user.recovery_codes_left} of 10 left</dd>
      <dt>Lockout</dt>
      <dd>
        {#if user.locked}
          Locked after too many wrong attempts
          <button class="link-button" type="button" disabled={busy} onclick={unlock}>Unlock now</button>
        {:else}
          Not locked
        {/if}
      </dd>
    </dl>

    <h3 class="check-title">Second factors</h3>
    {#if user.factors.length}
      <ul class="plain">
        {#each user.factors as factor (factor.id)}
          <li>
            {factor.label}
            <span class="muted">
              {factor.label === KIND_NAMES[factor.kind] ? "" : `· ${KIND_NAMES[factor.kind]} `}·
              added {date(factor.created_at)} · last used {dateTime(factor.last_used_at)}
            </span>
          </li>
        {/each}
      </ul>
    {:else}
      <p class="muted">None set up yet. They set one up at their next sign-in.</p>
    {/if}

    {#if isSelf}
      <p class="small muted">
        For your own password, second factors and sessions, use
        <a href={resolve("/account")}>Your account</a>.
      </p>
    {:else}
      <div class="button-row">
        <button class="button button-secondary" type="button" disabled={busy} onclick={() => ask({
          title: "Reset password",
          explain: `${user?.display_name} gets a new temporary password, and every session they have ends.`,
          confirm: "Reset password",
          path: "reset-password",
        })}>Reset password</button>
        <button class="button button-secondary" type="button" disabled={busy} onclick={() => ask({
          title: "Reset second factors",
          explain: `This removes ${user?.display_name}'s second factors and recovery codes, for a lost phone or key. They set up a new one at their next sign-in, and every session they have ends.`,
          confirm: "Reset second factors",
          path: "reset-second-factors",
        })}>Reset second factors</button>
        <button class="button button-secondary" type="button" disabled={busy ||
          !user.sessions.length} onclick={() => ask({
          title: "Sign out everywhere",
          explain: `Every session ${user?.display_name} has ends now.`,
          confirm: "Sign out everywhere",
          path: "sign-out",
        })}>Sign out everywhere</button>
      </div>
    {/if}
  </section>

  <section class="section">
    <h2 class="section-title">Sessions</h2>
    {#if user.sessions.length}
      <div class="table-wrap">
        <table class="table">
          <thead>
            <tr><th>Browser</th><th>Address</th><th>Signed in</th><th>Last active</th><th>Second factor</th></tr>
          </thead>
          <tbody>
            {#each user.sessions as row (row.id)}
              <tr>
                <td>{browserName(row.user_agent)}</td>
                <td class="mono">{row.ip ?? "—"}</td>
                <td>{dateTime(row.created_at)}</td>
                <td>{dateTime(row.last_seen_at)}</td>
                <td>{row.second_factor_done ? "Passed" : "Not yet"}</td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
    {:else}
      <p class="muted">Not signed in anywhere.</p>
    {/if}
  </section>
{/if}

<Dialog bind:open={confirmOpen} title={pending?.title ?? ""}>
  <p>{pending?.explain}</p>
  {#snippet actions()}
    <button class="button button-secondary" type="button" onclick={() => (confirmOpen = false)}>
      Cancel
    </button>
    <button class="button button-primary" type="button" onclick={confirmed}>{pending?.confirm}</button>
  {/snippet}
</Dialog>

<Dialog bind:open={temporaryOpen} title="New temporary password">
  {#if temporary}
    <TemporaryPasswordNotice name={temporary.user.display_name}
      password={temporary.temporary_password} expiresAt={temporary.expires_at} />
  {/if}
  {#snippet actions()}
    <button class="button button-primary" type="button" onclick={() => (temporaryOpen = false)}>
      Done
    </button>
  {/snippet}
</Dialog>

<style>
  .tags {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--space-2);
    margin-top: var(--space-1);
  }
  .columns {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
    gap: var(--space-6);
  }
  .roles {
    margin: 0;
    padding: 0;
    border: 0;
  }
  .roles legend {
    margin-bottom: var(--space-2);
  }
  .plain {
    margin: 0;
    padding-left: 1.2em;
  }
</style>
