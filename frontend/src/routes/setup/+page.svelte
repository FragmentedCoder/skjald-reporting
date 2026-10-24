<script lang="ts">
  import { goto } from "$app/navigation";
  import { resolve } from "$app/paths";
  import { onMount } from "svelte";
  import { api, ApiError } from "$lib/api";
  import AuthLayout from "$lib/components/AuthLayout.svelte";
  import PolicyFields from "$lib/components/PolicyFields.svelte";
  import SaveSecrets from "$lib/components/SaveSecrets.svelte";
  import SecondFactorSetup from "$lib/components/SecondFactorSetup.svelte";
  import VerifySecondFactor from "$lib/components/VerifySecondFactor.svelte";
  import type { SecuritySettings } from "$lib/policy";
  import { recoveryCodesText, recoveryKitText, type RecoveryKit } from "$lib/secrets";
  import {
    session,
    settle,
    useSession,
    type SecondFactorResult,
    type SessionInfo,
  } from "$lib/session.svelte";

  type Step =
    | "token"
    | "company"
    | "security"
    | "administrator"
    | "sign-in"
    | "second-factor"
    | "verify"
    | "codes"
    | "kit";
  const STEP_COUNT = 6;
  const STEP_NUMBER: Record<Step, number> = {
    token: 1,
    company: 2,
    security: 3,
    administrator: 4,
    "sign-in": 4,
    "second-factor": 5,
    verify: 5,
    codes: 5,
    kit: 6,
  };

  interface Progress {
    company_name: string | null;
    address: string;
    security_reviewed: boolean;
    security: SecuritySettings;
    administrator: string | null;
  }

  let ready = $state(false);
  let step = $state<Step>("token");
  let token = $state("");
  let progress = $state<Progress | null>(null);
  let companyName = $state("");
  let security = $state<SecuritySettings | null>(null);
  let admin = $state({ display_name: "", username: "", email: "", password: "", repeat: "" });
  let password = $state("");
  let codes = $state<string[]>([]);
  let kit = $state<RecoveryKit | null>(null);
  let error = $state<string | null>(null);
  let breachCheckDown = $state(false);
  let busy = $state(false);

  const eyebrow = $derived(`Step ${STEP_NUMBER[step]} of ${STEP_COUNT}`);
  const tokenHeader = $derived({ "X-Setup-Token": token });

  onMount(async () => {
    await settle("/setup");
    ready = session.setupNeeded;
  });

  async function run<T>(action: () => Promise<T>): Promise<T | null> {
    busy = true;
    error = null;
    try {
      return await action();
    } catch (e) {
      if (e instanceof ApiError && e.status === 410) {
        session.setupNeeded = false; // finished in another window
        await goto(resolve("/"));
        return null;
      }
      error = e instanceof ApiError ? e.message : "Something went wrong. Try again.";
      return null;
    } finally {
      busy = false;
    }
  }

  /** Where setup stands decides the next step, so a reload or a second visit resumes. */
  function nextStep() {
    const current = session.current;
    error = null;
    if (!progress) step = "token";
    else if (!progress.company_name) step = "company";
    else if (!progress.security_reviewed) step = "security";
    else if (!progress.administrator) step = "administrator";
    else if (current?.user.username !== progress.administrator) step = "sign-in";
    else if (current.second_factor === "enrol") step = "second-factor";
    else if (current.second_factor === "verify") step = "verify";
    else void showKit();
  }

  async function submitToken(event: SubmitEvent) {
    event.preventDefault();
    const found = await run(() => api<Progress>("POST", "/setup/progress", undefined, tokenHeader));
    if (!found) return;
    progress = found;
    companyName = found.company_name ?? "";
    security = { ...found.security };
    nextStep();
  }

  async function submitCompany(event: SubmitEvent) {
    event.preventDefault();
    const found = await run(() =>
      api<Progress>("POST", "/setup/company", { name: companyName }, tokenHeader),
    );
    if (!found) return;
    progress = found;
    nextStep();
  }

  async function submitSecurity(event: SubmitEvent) {
    event.preventDefault();
    const found = await run(() =>
      api<Progress>("POST", "/setup/security", security, tokenHeader),
    );
    if (!found) return;
    progress = found;
    nextStep();
  }

  async function createAdministrator(skipBreachCheck: boolean) {
    if (admin.password !== admin.repeat) {
      error = "The two passwords don't match.";
      return;
    }
    breachCheckDown = false;
    const info = await run(async () => {
      try {
        return await api<SessionInfo>(
          "POST",
          "/setup/administrator",
          {
            display_name: admin.display_name,
            username: admin.username,
            email: admin.email || null,
            password: admin.password,
            skip_breach_check: skipBreachCheck,
          },
          tokenHeader,
        );
      } catch (e) {
        if (e instanceof ApiError && e.status === 503) breachCheckDown = true;
        throw e;
      }
    });
    if (!info) return;
    useSession(info);
    if (progress) progress.administrator = info.user.username;
    admin.password = admin.repeat = "";
    nextStep();
  }

  async function submitSignIn(event: SubmitEvent) {
    event.preventDefault();
    const info = await run(() =>
      api<SessionInfo>("POST", "/auth/sign-in", { username: progress?.administrator, password }),
    );
    password = "";
    if (!info) return;
    useSession(info);
    nextStep();
  }

  function secondFactorDone(result: SecondFactorResult) {
    useSession(result.session);
    codes = result.recovery_codes ?? [];
    if (codes.length) step = "codes";
    else nextStep();
  }

  function verified(result: SecondFactorResult) {
    useSession(result.session);
    nextStep();
  }

  async function showKit() {
    step = "kit";
    kit = await run(() => api<RecoveryKit>("POST", "/setup/recovery-kit", undefined, tokenHeader));
  }

  async function finish() {
    const done = await run(() =>
      api("POST", "/setup/complete", { kit_saved: true }, tokenHeader),
    );
    if (!done) return;
    session.setupNeeded = false;
    await goto(resolve("/"));
  }
</script>

<svelte:head><title>Set up Skjald</title></svelte:head>

{#if ready}
  {#if step === "token"}
    <AuthLayout heading="Set up Skjald" {eyebrow}>
      <p class="muted">
        Enter the setup token Skjald printed when it started. On the server, it is in the output
        of <span class="mono">docker compose logs app</span>.
      </p>
      <form class="stack" onsubmit={submitToken}>
        {#if error}<p class="alert alert-critical" role="alert">{error}</p>{/if}
        <div class="field">
          <label for="token">Setup token</label>
          <input
            id="token"
            class="input code"
            autocomplete="off"
            autocapitalize="characters"
            spellcheck="false"
            required
            bind:value={token}
          />
        </div>
        <button class="button button-primary button-block" type="submit" disabled={busy}>
          Continue
        </button>
      </form>
    </AuthLayout>
  {:else if step === "company" && progress}
    <AuthLayout
      heading="Company and server"
      intro="Skjald works for one company. Its name appears in the app and on every report."
      {eyebrow}
    >
      <div class="address stack">
        <p class="check-title">Server address</p>
        <p class="mono">{progress.address}</p>
        <p class="small muted">
          Passkeys are tied to this address. If it isn't the one people will use, stop here,
          set <span class="mono">SKJALD_ADDRESS</span> on the server and restart Skjald.
        </p>
      </div>
      <form class="stack" onsubmit={submitCompany}>
        {#if error}<p class="alert alert-critical" role="alert">{error}</p>{/if}
        <div class="field">
          <label for="company">Company name</label>
          <input
            id="company"
            class="input"
            autocomplete="organization"
            required
            bind:value={companyName}
          />
        </div>
        <button class="button button-primary button-block" type="submit" disabled={busy}>
          Continue
        </button>
      </form>
    </AuthLayout>
  {:else if step === "security" && security}
    <AuthLayout
      heading="Security settings"
      intro="These defaults suit most teams. You can change them any time under Admin, Security."
      {eyebrow}
    >
      <form class="stack" onsubmit={submitSecurity}>
        {#if error}<p class="alert alert-critical" role="alert">{error}</p>{/if}
        <PolicyFields bind:values={security} />
        <button class="button button-primary button-block" type="submit" disabled={busy}>
          Continue
        </button>
      </form>
    </AuthLayout>
  {:else if step === "administrator"}
    <AuthLayout heading="Create the administrator" {eyebrow}>
      <p class="muted">
        This is the break-glass account: it works even when your directory is down, and every
        sign-in with it is flagged in the audit log. Use it for setup and emergencies, and give
        people their own accounts for daily work.
      </p>
      <form
        class="stack"
        onsubmit={(event) => {
          event.preventDefault();
          createAdministrator(false);
        }}
      >
        {#if breachCheckDown}
          <div class="alert alert-warning stack" role="alert">
            <p>
              Skjald couldn't reach api.pwnedpasswords.com to check the password against known
              data breaches. If this server has no internet access, you can continue without the
              check.
            </p>
            <button
              class="button button-secondary"
              type="button"
              disabled={busy}
              onclick={() => createAdministrator(true)}
            >
              Continue without the check
            </button>
          </div>
        {:else if error}
          <p class="alert alert-critical" role="alert">{error}</p>
        {/if}
        <div class="field">
          <label for="display-name">Full name</label>
          <input
            id="display-name"
            class="input"
            autocomplete="name"
            required
            bind:value={admin.display_name}
          />
        </div>
        <div class="field">
          <label for="username">Username</label>
          <input
            id="username"
            class="input"
            autocomplete="username"
            autocapitalize="none"
            spellcheck="false"
            required
            bind:value={admin.username}
          />
        </div>
        <div class="field">
          <label for="email">Email (optional)</label>
          <input
            id="email"
            class="input"
            type="email"
            autocomplete="email"
            bind:value={admin.email}
          />
        </div>
        <div class="field">
          <label for="password">Password</label>
          <input
            id="password"
            class="input"
            type="password"
            autocomplete="new-password"
            aria-describedby="password-hint"
            required
            bind:value={admin.password}
          />
          <span class="hint" id="password-hint">
            At least 12 characters. A few random words work well.
          </span>
        </div>
        <div class="field">
          <label for="repeat">Repeat password</label>
          <input
            id="repeat"
            class="input"
            type="password"
            autocomplete="new-password"
            required
            bind:value={admin.repeat}
          />
        </div>
        <button class="button button-primary button-block" type="submit" disabled={busy}>
          Create administrator
        </button>
      </form>
    </AuthLayout>
  {:else if step === "sign-in" && progress}
    <AuthLayout
      heading="Sign in as {progress.administrator}"
      intro="The administrator for this server is already created. Sign in to continue setup."
      {eyebrow}
    >
      <form class="stack" onsubmit={submitSignIn}>
        {#if error}<p class="alert alert-critical" role="alert">{error}</p>{/if}
        <div class="field">
          <label for="admin-password">Password</label>
          <input
            id="admin-password"
            class="input"
            type="password"
            autocomplete="current-password"
            required
            bind:value={password}
          />
        </div>
        <button class="button button-primary button-block" type="submit" disabled={busy}>
          Sign in
        </button>
      </form>
    </AuthLayout>
  {:else if step === "second-factor" && session.current}
    <AuthLayout
      heading="Protect the administrator"
      intro="Every account needs a second step at sign-in. Set one up for {session.current.user
        .username} now."
      {eyebrow}
    >
      <SecondFactorSetup onDone={secondFactorDone} />
    </AuthLayout>
  {:else if step === "verify" && session.current}
    <AuthLayout heading="Confirm it's you" {eyebrow}>
      <VerifySecondFactor info={session.current} onDone={verified} />
    </AuthLayout>
  {:else if step === "codes" && session.current}
    <AuthLayout
      heading="Save your recovery codes"
      intro="If you lose your phone or key, each code lets you sign in once. They are shown only now."
      {eyebrow}
    >
      <SaveSecrets
        text={recoveryCodesText(session.current.user.username, codes)}
        filename="skjald-recovery-codes.txt"
        confirmation="I have saved these codes somewhere safe"
        onContinue={nextStep}
      >
        <ol class="codes mono">
          {#each codes as code (code)}<li>{code}</li>{/each}
        </ol>
      </SaveSecrets>
    </AuthLayout>
  {:else if step === "kit"}
    <AuthLayout heading="Save the recovery kit" {eyebrow}>
      <p class="muted">
        These two keys unlock this server's data and its backups. Without them, no backup can be
        restored. Keep them offline or in your password manager, never on this server. They are
        shown only during setup.
      </p>
      {#if error}<p class="alert alert-critical" role="alert">{error}</p>{/if}
      {#if kit}
        <SaveSecrets
          text={recoveryKitText(kit)}
          filename="skjald-recovery-kit.txt"
          confirmation="I have saved the recovery kit somewhere safe, away from this server"
          continueLabel="Finish setup"
          {busy}
          onContinue={finish}
        >
          <dl class="kit">
            <dt>Master key</dt>
            <dd class="mono">{kit.master_key}</dd>
            <dt>Backup key</dt>
            <dd class="mono">{kit.backup_key}</dd>
          </dl>
        </SaveSecrets>
      {/if}
    </AuthLayout>
  {/if}
{/if}

<style>
  .address {
    gap: var(--space-1);
    padding: var(--space-4);
    border-radius: var(--radius-md);
    background: var(--surface-subtle);
  }
  .kit {
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
    margin: 0;
    padding: var(--space-4);
    border-radius: var(--radius-md);
    background: var(--surface-subtle);
  }
  .kit dt {
    font: var(--type-label);
  }
  .kit dd {
    margin: 0 0 var(--space-2);
    overflow-wrap: normal;
  }
</style>
