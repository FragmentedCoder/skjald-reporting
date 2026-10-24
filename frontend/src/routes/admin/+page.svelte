<script lang="ts">
  import { goto } from "$app/navigation";
  import { resolve } from "$app/paths";
  import { onMount } from "svelte";
  import { can, session } from "$lib/session.svelte";

  // The admin panel opens on the first section the user may see.
  onMount(() => {
    if (can(session.current, "administer")) goto(resolve("/admin/users"), { replaceState: true });
    else if (can(session.current, "read_audit_log")) {
      goto(resolve("/admin/audit"), { replaceState: true });
    }
  });
</script>
