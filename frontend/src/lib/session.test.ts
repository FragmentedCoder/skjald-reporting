import { describe, expect, it } from "vitest";
import { placeFor, type SessionInfo } from "./session.svelte";

function sessionIn(
  second_factor: SessionInfo["second_factor"],
  password_change_required = false,
): SessionInfo {
  return {
    user: {
      id: 1,
      username: "astrid",
      display_name: "Astrid Fjeld",
      theme: "system",
      roles: [],
      capabilities: [],
    },
    second_factor,
    methods: [],
    password_change_required,
    csrf_token: "t",
    expires_at: "2026-10-24T12:00:00Z",
  };
}

describe("placeFor", () => {
  it.each([
    [null, "/sign-in"],
    [sessionIn("enrol"), "/sign-in/set-up"],
    [sessionIn("verify"), "/sign-in/verify"],
    [sessionIn("done"), "/"],
  ])("sends %o to %s", (info, place) => {
    expect(placeFor(info, false)).toBe(place);
  });

  it("asks for a new password before setting up a second factor", () => {
    expect(placeFor(sessionIn("enrol", true), false)).toBe("/sign-in/new-password");
  });

  it("asks for the second factor already set up before a new password", () => {
    expect(placeFor(sessionIn("verify", true), false)).toBe("/sign-in/verify");
    expect(placeFor(sessionIn("done", true), false)).toBe("/sign-in/new-password");
  });

  it("sends everyone to the setup wizard until setup is finished", () => {
    for (const info of [null, sessionIn("enrol"), sessionIn("done")]) {
      expect(placeFor(info, true)).toBe("/setup");
    }
  });
});
