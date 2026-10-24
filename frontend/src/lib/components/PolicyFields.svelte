<script lang="ts">
  // The security policy's fields, shared by the setup wizard and the admin panel.
  import type { SecuritySettings } from "$lib/policy";

  type NumberField = Exclude<keyof SecuritySettings, "breach_check_enabled">;

  // The same limits as backend/app/policy.py LIMITS; the server checks them too.
  const FIELDS: { key: NumberField; label: string; hint: string; min: number; max: number }[] = [
    {
      key: "min_password_length",
      label: "Minimum password length",
      hint: "Characters. Skjald has no rules about character types: length and the breach check protect better (ASVS 6.2).",
      min: 8,
      max: 64,
    },
    {
      key: "lockout_threshold",
      label: "Lock an account after",
      hint: "Wrong passwords or codes in a row.",
      min: 3,
      max: 50,
    },
    {
      key: "lockout_minutes",
      label: "Keep it locked for",
      hint: "Minutes. An administrator can unlock it sooner.",
      min: 1,
      max: 1440,
    },
    {
      key: "idle_timeout_minutes",
      label: "Sign out after inactivity",
      hint: "Minutes without any activity.",
      min: 5,
      max: 720,
    },
    {
      key: "max_session_hours",
      label: "Sign out after at most",
      hint: "Hours, however active. People then sign in again.",
      min: 1,
      max: 72,
    },
  ];

  let { values = $bindable() }: { values: SecuritySettings } = $props();
</script>

<label class="toggle">
  <input type="checkbox" bind:checked={values.breach_check_enabled} />
  <span>
    <span class="toggle-title">Check new passwords against known data breaches</span>
    <span class="small muted">
      Uses Have I Been Pwned. Only the first 5 characters of a hash of the password leave the
      server. Needs internet access to api.pwnedpasswords.com.
    </span>
  </span>
</label>

{#each FIELDS as field (field.key)}
  <div class="field">
    <label for={field.key}>{field.label}</label>
    <input
      id={field.key}
      class="input number"
      type="number"
      min={field.min}
      max={field.max}
      required
      aria-describedby="{field.key}-hint"
      bind:value={values[field.key]}
    />
    <span class="hint" id="{field.key}-hint">{field.hint} From {field.min} to {field.max}.</span>
  </div>
{/each}

<style>
  .toggle {
    display: flex;
    align-items: flex-start;
    gap: var(--space-3);
  }
  .toggle input {
    flex: none;
    width: 18px;
    height: 18px;
    margin-top: 3px;
    accent-color: var(--link);
  }
  .toggle-title {
    display: block;
    font: var(--type-label);
  }
  .number {
    max-width: 10rem;
  }
</style>
