<script lang="ts">
  // A status pill: always a word, never colour alone (docs/brand).
  let {
    tone = "neutral",
    text,
  }: { tone?: "ok" | "warning" | "critical" | "info" | "neutral"; text: string } = $props();
</script>

<span class="pill {tone}">{text}</span>

<style>
  .pill {
    display: inline-block;
    padding: 2px 10px;
    border-radius: var(--radius-pill);
    font: var(--type-body-sm);
    font-weight: 500;
    white-space: nowrap;
  }
  .ok {
    background: var(--ok-bg);
    color: var(--ok-text);
  }
  .warning {
    background: var(--warning-bg);
    color: var(--warning-text);
  }
  .critical {
    background: var(--critical-bg);
    color: var(--critical-text);
  }
  .info {
    background: var(--info-bg);
    color: var(--info-text);
  }
  .neutral {
    background: var(--surface-subtle);
    color: var(--text-muted);
  }
</style>
