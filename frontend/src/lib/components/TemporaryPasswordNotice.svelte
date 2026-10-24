<script lang="ts">
  import { dateTime } from "$lib/format";

  let {
    name,
    password,
    expiresAt,
  }: { name: string; password: string; expiresAt: string } = $props();

  let copied = $state(false);

  async function copy() {
    await navigator.clipboard.writeText(password);
    copied = true;
  }
</script>

<div class="notice stack">
  <p>
    Give {name} this temporary password, by phone or in person rather than by email. It works
    once, until {dateTime(expiresAt)}, and they choose their own password when they sign in.
  </p>
  <p class="password mono" aria-label="Temporary password">{password}</p>
  <div>
    <button class="button button-secondary" type="button" onclick={copy}>
      {copied ? "Copied" : "Copy password"}
    </button>
  </div>
  <p class="small muted">It is shown only now. If it gets lost, reset the password again.</p>
</div>

<style>
  .notice {
    padding: var(--space-4);
    border-radius: var(--radius-md);
    background: var(--surface-subtle);
  }
  .password {
    font-size: 18px;
    letter-spacing: 0.05em;
  }
</style>
