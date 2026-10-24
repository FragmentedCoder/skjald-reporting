<script lang="ts">
  import type { Snippet } from "svelte";
  import Mark from "./Mark.svelte";

  let {
    heading,
    intro,
    eyebrow,
    children,
    footer,
  }: {
    heading: string;
    intro?: string;
    eyebrow?: string;
    children: Snippet;
    footer?: Snippet;
  } = $props();
</script>

<main class="page">
  <div class="card">
    <header class="brand">
      <Mark size={40} />
      <span class="wordmark">Skjald</span>
    </header>
    <div class="heading">
      {#if eyebrow}<p class="eyebrow muted">{eyebrow}</p>{/if}
      <h1 class="title">{heading}</h1>
    </div>
    {#if intro}<p class="muted">{intro}</p>{/if}
    {@render children()}
    {#if footer}
      <footer class="footer">{@render footer()}</footer>
    {/if}
  </div>
</main>

<style>
  .page {
    display: grid;
    place-items: center;
    min-height: 100vh;
    padding: var(--space-6) var(--space-4);
  }
  .card {
    display: flex;
    flex-direction: column;
    gap: var(--space-4);
    width: 100%;
    max-width: 440px;
    padding: var(--space-8);
    border: 1px solid var(--border);
    border-radius: var(--radius-lg);
    background: var(--surface);
  }
  .brand {
    display: flex;
    align-items: center;
    gap: var(--space-3);
    margin-bottom: var(--space-2);
  }
  .wordmark {
    font: var(--type-subheading);
  }
  .heading {
    display: flex;
    flex-direction: column;
    gap: var(--space-1);
  }
  .eyebrow {
    font: var(--type-overline);
    letter-spacing: var(--type-overline-tracking);
    text-transform: uppercase;
  }
  .footer {
    display: flex;
    justify-content: space-between;
    gap: var(--space-4);
    padding-top: var(--space-4);
    border-top: 1px solid var(--border);
  }
  @media (max-width: 480px) {
    .card {
      padding: var(--space-6);
    }
  }
</style>
