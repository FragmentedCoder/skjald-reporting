<script lang="ts">
  import { onMount } from "svelte";
  import { api, ApiError } from "$lib/api";
  import AppShell from "$lib/components/AppShell.svelte";
  import Dialog from "$lib/components/Dialog.svelte";
  import Pill from "$lib/components/Pill.svelte";
  import SaveSecrets from "$lib/components/SaveSecrets.svelte";
  import SecondFactorSetup from "$lib/components/SecondFactorSetup.svelte";
  import { browserName, date, dateTime } from "$lib/format";
  import { recoveryCodesText } from "$lib/secrets";
  import {
    applyTheme,
    session,
    sessionEnded,
    settle,
    useSession,
    type SecondFactorResult,
    type SessionInfo,
    type Theme,
  } from "$lib/session.svelte";

  interface Factor {
    id: number;
    kind: "totp" | "webauthn";
    label: string;
    created_at: string;
    last_used_at: string | null;
  }
  interface SessionRow {
    id: number;
    created_at: string;
    last_seen_at: string;
    ip: string | null;
    user_agent: string | null;
    current: boolean;
  }
  interface Account {
    username: string;
    display_name: string;
    email: string | null;
    theme: Theme;
    password_changed_at: string | null;
    factors: Factor[];
    recovery_codes_left: number;
    sessions: SessionRow[];
  }

  const KIND_NAMES = { totp: "Authenticator app", webauthn: "Passkey or security key" };

  let info = $state<SessionInfo | null>(null);
  let account = $state<Account | null>(null);
  let profile = $state({ display_name: "", email: "", theme: "system" as Theme });
  let passwords = $state({ current: "", next: "", repeat: "" });
  let notice = $state<{ section: string; tone: "ok" | "critical"; text: string } | null>(null);
  let busy = $state(false);

  // Re-entering the password guards removing a factor and new recovery codes.
  let confirming = $state<{ title: string; run: (password: string) => Promise<void> } | null>(
    null,
  );
  let confirmOpen = $state(false);
  let confirmPassword = $state("");
  let confirmError = $state<string | null>(null);
  let adding = $state(false);
  let newCodes = $state<string[] | null>(null);
  let codesOpen = $state(false);

  onMount(async () => {
    info = await settle("app");
    if (info) await load();
  });

  async function load() {
    account = await api<Account>("GET", "/account");
    profile = {
      display_name: account.display_name,
      email: account.email ?? "",
      theme: account.theme,
    };
  }

  async function guarded(section: string, action: () => Promise<void>) {
    busy = true;
    notice = null;
    try {
      await action();
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) {
        await sessionEnded(e.message);
        return;
      }
      notice = {
        section,
        tone: "critical",
        text: e instanceof ApiError ? e.message : "Something went wrong. Try again.",
      };
    } finally {
      busy = false;
    }
  }

  function saveProfile(event: SubmitEvent) {
    event.preventDefault();
    guarded("profile", async () => {
      account = await api<Account>("PATCH", "/account", {
        display_name: profile.display_name,
        email: profile.email,
        theme: profile.theme,
      });
      if (session.current) {
        session.current.user.display_name = account.display_name;
        session.current.user.theme = account.theme;
      }
      applyTheme(account.theme);
      notice = { section: "profile", tone: "ok", text: "Saved." };
    });
  }

  function changePassword(event: SubmitEvent) {
    event.preventDefault();
    if (passwords.next !== passwords.repeat) {
      notice = { section: "password", tone: "critical", text: "The two new passwords don't match." };
      return;
    }
    guarded("password", async () => {
      useSession(
        await api<SessionInfo>("POST", "/account/password", {
          current_password: passwords.current,
          new_password: passwords.next,
        }),
      );
      passwords = { current: "", next: "", repeat: "" };
      await load();
      notice = {
        section: "password",
        tone: "ok",
        text: "Your password is changed. Any other sessions were signed out.",
      };
    });
  }

  function askPassword(title: string, run: (password: string) => Promise<void>) {
    confirming = { title, run };
    confirmPassword = "";
    confirmError = null;
    confirmOpen = true;
  }

  async function confirm(event: SubmitEvent) {
    event.preventDefault();
    if (!confirming) return;
    busy = true;
    confirmError = null;
    try {
      await confirming.run(confirmPassword);
      confirmOpen = false;
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) {
        await sessionEnded(e.message);
        return;
      }
      confirmError = e instanceof ApiError ? e.message : "Something went wrong. Try again.";
    } finally {
      confirmPassword = "";
      busy = false;
    }
  }

  function removeFactor(factor: Factor) {
    askPassword(`Remove “${factor.label}”`, async (password) => {
      account = await api<Account>("POST", `/account/factors/${factor.id}/remove`, { password });
    });
  }

  function regenerateCodes() {
    askPassword("Get new recovery codes", async (password) => {
      const result = await api<{ recovery_codes: string[] }>("POST", "/account/recovery-codes", {
        password,
      });
      newCodes = result.recovery_codes;
      codesOpen = true;
      await load();
    });
  }

  async function factorAdded(result: SecondFactorResult) {
    useSession(result.session);
    adding = false;
    await load();
  }

  function endOtherSessions() {
    guarded("sessions", async () => {
      account = await api<Account>("POST", "/account/sessions/end-others");
      notice = { section: "sessions", tone: "ok", text: "Other sessions are signed out." };
    });
  }
</script>

<svelte:head><title>Your account · Skjald</title></svelte:head>

{#snippet message(section: string)}
  {#if notice?.section === section}
    <p class="alert alert-{notice.tone}" role={notice.tone === "critical" ? "alert" : "status"}>
      {notice.text}
    </p>
  {/if}
{/snippet}

{#if info && account}
  <AppShell {info}>
    <main class="page-content">
      <div class="page-header">
        <div>
          <h1 class="title">Your account</h1>
          <p class="small muted">Signed in as <span class="mono">{account.username}</span></p>
        </div>
      </div>

      <section class="section" aria-labelledby="profile-title">
        <h2 class="section-title" id="profile-title">Profile</h2>
        {@render message("profile")}
        <form class="stack form-narrow" onsubmit={saveProfile}>
          <div class="field">
            <label for="display-name">Full name</label>
            <input id="display-name" class="input" autocomplete="name" required
              bind:value={profile.display_name} />
          </div>
          <div class="field">
            <label for="email">Email</label>
            <input id="email" class="input" type="email" autocomplete="email"
              bind:value={profile.email} />
          </div>
          <fieldset class="themes">
            <legend class="check-title">Appearance</legend>
            {#each [["system", "Same as this device"], ["light", "Light"], ["dark", "Dark"]] as [value, label] (value)}
              <label class="check">
                <input type="radio" name="theme" {value} bind:group={profile.theme} />
                <span>{label}</span>
              </label>
            {/each}
          </fieldset>
          <div><button class="button button-primary" type="submit" disabled={busy}>Save</button></div>
        </form>
      </section>

      <section class="section" aria-labelledby="password-title">
        <h2 class="section-title" id="password-title">Password</h2>
        <p class="small muted">Last changed {dateTime(account.password_changed_at)}.</p>
        {@render message("password")}
        <form class="stack form-narrow" onsubmit={changePassword}>
          <input type="text" class="visually-hidden" autocomplete="username"
            value={account.username} readonly tabindex="-1" aria-hidden="true" />
          <div class="field">
            <label for="current-password">Current password</label>
            <input id="current-password" class="input" type="password"
              autocomplete="current-password" required bind:value={passwords.current} />
          </div>
          <div class="field">
            <label for="new-password">New password</label>
            <input id="new-password" class="input" type="password" autocomplete="new-password"
              required bind:value={passwords.next} />
          </div>
          <div class="field">
            <label for="repeat-password">Repeat new password</label>
            <input id="repeat-password" class="input" type="password" autocomplete="new-password"
              required bind:value={passwords.repeat} />
          </div>
          <div>
            <button class="button button-primary" type="submit" disabled={busy}>
              Change password
            </button>
          </div>
        </form>
      </section>

      <section class="section" aria-labelledby="factors-title">
        <h2 class="section-title" id="factors-title">Second factors</h2>
        {@render message("factors")}
        <div class="table-wrap">
          <table class="table">
            <thead>
              <tr><th>Name</th><th>Kind</th><th>Added</th><th>Last used</th><th></th></tr>
            </thead>
            <tbody>
              {#each account.factors as factor (factor.id)}
                <tr>
                  <td>{factor.label}</td>
                  <td>{KIND_NAMES[factor.kind]}</td>
                  <td>{date(factor.created_at)}</td>
                  <td>{dateTime(factor.last_used_at)}</td>
                  <td class="end">
                    <button class="link-button" type="button" disabled={account.factors.length < 2}
                      onclick={() => removeFactor(factor)}>Remove</button>
                  </td>
                </tr>
              {/each}
            </tbody>
          </table>
        </div>
        {#if account.factors.length < 2}
          <p class="small muted">Add another before removing your only second factor.</p>
        {/if}
        <div>
          <button class="button button-secondary" type="button" onclick={() => (adding = true)}>
            Add a second factor
          </button>
        </div>
      </section>

      <section class="section" aria-labelledby="codes-title">
        <h2 class="section-title" id="codes-title">Recovery codes</h2>
        <p>
          <Pill tone={account.recovery_codes_left > 2 ? "ok" : "warning"}
            text="{account.recovery_codes_left} of 10 left" />
        </p>
        <p class="small muted">
          Each code lets you sign in once if you lose your second factor. New codes replace all
          the old ones.
        </p>
        <div>
          <button class="button button-secondary" type="button" onclick={regenerateCodes}>
            Get new codes
          </button>
        </div>
      </section>

      <section class="section" aria-labelledby="sessions-title">
        <h2 class="section-title" id="sessions-title">Where you're signed in</h2>
        {@render message("sessions")}
        <div class="table-wrap">
          <table class="table">
            <thead>
              <tr><th>Browser</th><th>Address</th><th>Signed in</th><th>Last active</th></tr>
            </thead>
            <tbody>
              {#each account.sessions as row (row.id)}
                <tr>
                  <td>
                    {browserName(row.user_agent)}
                    {#if row.current}<Pill tone="info" text="This browser" />{/if}
                  </td>
                  <td class="mono">{row.ip ?? "—"}</td>
                  <td>{dateTime(row.created_at)}</td>
                  <td>{dateTime(row.last_seen_at)}</td>
                </tr>
              {/each}
            </tbody>
          </table>
        </div>
        <div>
          <button class="button button-secondary" type="button" disabled={busy ||
            account.sessions.length < 2} onclick={endOtherSessions}>
            Sign out other sessions
          </button>
        </div>
      </section>
    </main>
  </AppShell>

  <Dialog bind:open={confirmOpen} title={confirming?.title ?? ""}>
    <form class="stack" onsubmit={confirm}>
      {#if confirmError}<p class="alert alert-critical" role="alert">{confirmError}</p>{/if}
      <div class="field">
        <label for="confirm-password">Your password</label>
        <input id="confirm-password" class="input" type="password"
          autocomplete="current-password" required bind:value={confirmPassword} />
        <span class="hint">To make sure it's you.</span>
      </div>
      <div class="button-row">
        <button class="button button-primary" type="submit" disabled={busy}>Confirm</button>
        <button class="button button-secondary" type="button" onclick={() => (confirmOpen = false)}>
          Cancel
        </button>
      </div>
    </form>
  </Dialog>

  <Dialog bind:open={adding} title="Add a second factor">
    {#if adding}<SecondFactorSetup onDone={factorAdded} />{/if}
    <div>
      <button class="button button-secondary" type="button" onclick={() => (adding = false)}>
        Cancel
      </button>
    </div>
  </Dialog>

  <Dialog bind:open={codesOpen} title="Your new recovery codes">
    {#if newCodes}
      <SaveSecrets
        text={recoveryCodesText(account.username, newCodes)}
        filename="skjald-recovery-codes.txt"
        confirmation="I have saved these codes somewhere safe"
        continueLabel="Done"
        onContinue={() => {
          codesOpen = false;
          newCodes = null;
        }}
      >
        <ol class="codes mono">
          {#each newCodes as code (code)}<li>{code}</li>{/each}
        </ol>
      </SaveSecrets>
    {/if}
  </Dialog>
{/if}

<style>
  .themes {
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
    margin: 0;
    padding: 0;
    border: 0;
  }
  .themes legend {
    margin-bottom: var(--space-2);
  }
  .end {
    text-align: right;
  }
</style>
