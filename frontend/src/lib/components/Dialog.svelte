<script lang="ts">
  import type { Snippet } from "svelte";

  // A modal built on <dialog>: the browser handles focus, Escape and the backdrop.
  let {
    open = $bindable(false),
    title,
    children,
    actions,
  }: { open?: boolean; title: string; children: Snippet; actions?: Snippet } = $props();

  const titleId = $props.id();
  let dialog: HTMLDialogElement;

  $effect(() => {
    if (open && !dialog.open) dialog.showModal();
    else if (!open && dialog.open) dialog.close();
  });
</script>

<dialog bind:this={dialog} aria-labelledby={titleId} onclose={() => (open = false)}>
  <div class="body">
    <h2 id={titleId} class="dialog-title">{title}</h2>
    {@render children()}
    {#if actions}<div class="actions">{@render actions()}</div>{/if}
  </div>
</dialog>

<style>
  dialog {
    width: min(480px, calc(100vw - 2 * var(--space-4)));
    padding: 0;
    border: 1px solid var(--border);
    border-radius: var(--radius-lg);
    background: var(--surface);
    color: var(--text);
  }
  dialog::backdrop {
    background: rgb(11 20 32 / 0.55);
  }
  .body {
    display: flex;
    flex-direction: column;
    gap: var(--space-4);
    padding: var(--space-6);
  }
  .dialog-title {
    font: var(--type-subheading);
  }
  .actions {
    display: flex;
    flex-wrap: wrap;
    justify-content: flex-end;
    gap: var(--space-2);
  }
</style>
