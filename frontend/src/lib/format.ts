const DATE_TIME = new Intl.DateTimeFormat("en-GB", { dateStyle: "medium", timeStyle: "short" });
const DATE = new Intl.DateTimeFormat("en-GB", { dateStyle: "medium" });

/** "24 Oct 2026, 14:05" in the viewer's time zone; "Never" when there is no date. */
export function dateTime(iso: string | null | undefined, empty = "Never"): string {
  return iso ? DATE_TIME.format(new Date(iso)) : empty;
}

export function date(iso: string | null | undefined, empty = "—"): string {
  return iso ? DATE.format(new Date(iso)) : empty;
}

/** A short, readable name for a browser from its user agent. */
export function browserName(userAgent: string | null): string {
  if (!userAgent) return "Unknown browser";
  const known: [RegExp, string][] = [
    [/Edg\//, "Edge"],
    [/Firefox\//, "Firefox"],
    [/Chrome\//, "Chrome"],
    [/Safari\//, "Safari"],
  ];
  const name = known.find(([pattern]) => pattern.test(userAgent))?.[1] ?? "Browser";
  const system = /Windows/.test(userAgent)
    ? "Windows"
    : /Mac OS X/.test(userAgent)
      ? "macOS"
      : /Android/.test(userAgent)
        ? "Android"
        : /iPhone|iPad/.test(userAgent)
          ? "iOS"
          : /Linux/.test(userAgent)
            ? "Linux"
            : null;
  return system ? `${name} on ${system}` : name;
}
