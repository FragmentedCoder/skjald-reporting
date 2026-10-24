<script lang="ts">
  import type { Snippet } from "svelte";

  // Secrets shown once (recovery codes, the recovery kit): copy, download, and
  // confirm they are saved before going on.
  let {
    text,
    filename,
    confirmation,
    continueLabel = "Continue",
    busy = false,
    onContinue,
    children,
  }: {
    text: string;
    filename: string;
    confirmation: string;
    continueLabel?: string;
    busy?: boolean;
    onContinue: () => void;
    children: Snippet;
  } = $props();

  let saved = $state(false);
  let copied = $state(false);

  async function copy() {
    await navigator.clipboard.writeText(text);
    copied = true;
  }

  function download() {
    const link = document.createElement("a");
    link.href = URL.createObjectURL(new Blob([text], { type: "text/plain" }));
    link.download = filename;
    link.click();
    // Revoking in the same tick can cancel the download in some browsers.
    setTimeout(() => URL.revokeObjectURL(link.href), 0);
  }
</script>

{@render children()}
<div class="actions">
  <button class="button button-secondary" type="button" onclick={copy}>
    {copied ? "Copied" : "Copy"}
  </button>
  <button class="button button-secondary" type="button" onclick={download}>Download</button>
</div>
<label class="confirm">
  <input type="checkbox" bind:checked={saved} />
  <span>{confirmation}</span>
</label>
<button
  class="button button-primary button-block"
  type="button"
  disabled={!saved || busy}
  onclick={onContinue}
>
  {continueLabel}
</button>

<style>
  .actions {
    display: flex;
    gap: var(--space-2);
  }
  .confirm {
    display: flex;
    align-items: flex-start;
    gap: var(--space-2);
  }
  .confirm input {
    flex: none;
    width: 18px;
    height: 18px;
    margin-top: 3px;
    accent-color: var(--link);
  }
</style>
