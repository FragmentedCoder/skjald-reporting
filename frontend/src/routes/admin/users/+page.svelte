<script lang="ts">
  import { resolve } from "$app/paths";
  import UserPlus from "@lucide/svelte/icons/user-plus";
  import { onMount } from "svelte";
  import { api, ApiError } from "$lib/api";
  import { userStatus, type UserSummary } from "$lib/admin";
  import Pill from "$lib/components/Pill.svelte";
  import { dateTime } from "$lib/format";
  import { roleName } from "$lib/roles";

  let users = $state<UserSummary[] | null>(null);
  let error = $state<string | null>(null);

  onMount(async () => {
    try {
      users = await api<UserSummary[]>("GET", "/admin/users");
    } catch (e) {
      error = e instanceof ApiError ? e.message : "The users could not be loaded.";
    }
  });
</script>

<svelte:head><title>Users · Admin · Skjald</title></svelte:head>

<div class="page-header">
  <div>
    <h1 class="title">Users</h1>
    <p class="small muted">Everyone who can sign in, and what their roles let them do.</p>
  </div>
  <a class="button button-primary" href={resolve("/admin/users/new")}>
    <UserPlus size={18} aria-hidden="true" />
    Add user
  </a>
</div>

{#if error}<p class="alert alert-critical" role="alert">{error}</p>{/if}

{#if users}
  <div class="section table-wrap">
    <table class="table">
      <thead>
        <tr><th>Name</th><th>Roles</th><th>Status</th><th>Second factor</th><th>Last sign-in</th></tr>
      </thead>
      <tbody>
        {#each users as user (user.id)}
          {@const status = userStatus(user)}
          <tr>
            <td>
              <a class="row-link" href={resolve("/admin/users/[id]", { id: String(user.id) })}>
                {user.display_name}
              </a>
              <div class="small muted mono">{user.username}</div>
            </td>
            <td>
              {user.roles.map(roleName).join(", ") || "No roles"}
              {#if user.is_break_glass}<div><Pill tone="info" text="Break-glass" /></div>{/if}
            </td>
            <td><Pill tone={status.tone} text={status.text} /></td>
            <td>{user.second_factors ? `${user.second_factors} set up` : "None"}</td>
            <td>{dateTime(user.last_sign_in_at)}</td>
          </tr>
        {/each}
      </tbody>
    </table>
  </div>
{/if}
