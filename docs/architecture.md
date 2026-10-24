# Skjald architecture

This document describes how Skjald is designed. It is the reference for contributors and is updated as the design changes. Phase 0 is done and Phase 1 is in progress; see the roadmap at the end.

## Principles

- **One issuing company per install.** No multi-tenancy. Another company runs its own install.
- **Internal by default.** The app is reachable only on the internal network. The only part ever exposed to the internet is the optional Bifrost delivery gateway, which stores files it cannot read.
- **Security first.** Per-customer encryption keys, MFA for every account, need-to-know access and a tamper-evident audit log. The engineering baseline is OWASP ASVS Level 2.
- **Templates are files.** Every template, built-in or custom, exports and imports as one `.skjald` file.
- **Easy to install.** One command on a fresh Ubuntu Server LTS VM, plus a verifiable install path.
- **Reports worth keeping.** Signed, timestamped PDF/A files that still verify years later.

## Data model

```mermaid
flowchart TD
    Company["Company<br/>one per install"] -->|has many| Customer["Customer<br/>sites, contacts, own key"]
    Customer -->|has many| Project["Project<br/>assigned technicians"]
    Project -->|has many| Report["Report<br/>revisions, signatures, deliveries"]
    subgraph Library
        Templates["Templates<br/>frozen published versions"]
        Shared["Shared library<br/>variables, text snippets, data tables"]
        Styles["Styles"]
    end
    Library -->|pinned version, allowed style| Report
```

- **Customer:** name, CVR, address, sites, contacts, logo, report language, default style, retention period, custom fields.
- **Project:** name, number, sites, dates, responsible technician, customer contact, classification, custom fields. An archived project and its reports are read-only.
- **Report:** numbered per type and year (for example `INC-2026-0142`) and pinned to one template version.

## Roles

| Role | Can |
| --- | --- |
| Administrator | Everything, including all customers, users, policies, keys, backups and breaking checkouts |
| Report Designer | Build templates, custom fields and styles; edit the shared library |
| Technician | Create projects and reports for assigned customers, fill them in, upload data, sign, deliver; add and change shared library entries; check signed reports |
| Reviewer | Review and countersign reports for assigned customers |
| Auditor | Read the audit log and report metadata |

Access to customer data is assignment-based. Nobody can review or countersign their own report.

### Administration

- **Users.** Administrators add people with their roles; Skjald makes a random one-time temporary password (ASVS 6.4) that works for 7 days and must be replaced before the app opens. If the account already has a second factor, that is asked for first. Administrators edit details, roles and active status; reset a password (signs the person out everywhere) or second factors (for a lost phone or key); unlock an account; end its sessions; and see its sessions and factors. They can't disable themselves or drop their own Administrator role, and the break-glass Administrator always keeps that role and stays active, so an active Administrator always remains. Actions on yourself go through Your account.
- **Security settings.** The password and session policy, each within fixed limits, and the admin IP allowlist. The allowlist is enforced in the app for every admin route (enforcing it at Caddy as well comes with the installer); a list that would leave out the saver's own address is refused, and `docker compose exec app python -m app.console reset-allowlist` on the VM clears it.
- **Audit log viewer.** Administrators and Auditors filter by action or group, person and dates, check the chain, and export CSV. Exported cells that a spreadsheet would read as a formula are prefixed with `'` (CSV injection), and every export is itself logged.
- **Your account.** Name, email, appearance (system, light or dark, stored per user), password, second factors and recovery codes, and sessions. Removing a factor (never the last) and new recovery codes need the password again; a wrong one counts towards the lockout. Changing the password signs out every other session and gives this one a new token.

Routes ask for a capability (such as "administer" or "read the audit log"), never a role; `backend/app/roles.py` holds the one table of which roles grant which capability, and a test checks it against the spec. A refused request is written to the audit log. A person can hold several roles, and every grant is logged with who made it. Customer assignments arrive with customers.

## Report lifecycle

```mermaid
stateDiagram-v2
    [*] --> Draft
    Draft --> InReview: sent for review
    Draft --> Signing: review optional, skipped
    InReview --> Draft: changes requested
    InReview --> Signing: approved
    Signing --> Signed: all signatures added
    Signed --> Delivered
    Delivered --> Archived: project archived
    Signed --> Draft: correction creates revision v2
```

Technicians check out a section or a whole report before editing. Administrators can break stale checkouts. A signed report is locked; a correction becomes a new revision and the old one is kept as superseded.

## Templates

Only Administrators and Report Designers see the template builder. It has three tabs, and every element in it is labelled with who sees it: **Form** (the technician, while filling in), **PDF** (the customer) or **Builder only**.

- **Questions** — the form a technician fills in, in steps: fields, help text, validation, defaults and repeating groups. Each question shows which PDF blocks print it.
- **Layout** — the PDF, built by drag and drop from blocks: sections, headings, text with variables, answers, tables bound to repeating groups, images, callouts, sources, page breaks and signature boxes, plus the cover, table of contents and repeated sections. Every major section starts on its own page by default (a per-section setting), headings are never left alone at the foot of a page, table rows never split and table headers repeat on each page.
- **Data** — every name a template can read, with what it is, where it comes from and an example: company, customer, project, report, answers, the shared library and calculated values, plus a reference for each function.

A "Try it" view shows the technician's screen for the draft template, with sample answers, before it is published.

Each block has its own settings, all printed in the PDF:

| Block | Settings |
| --- | --- |
| Section | Title, an introduction under the heading, start on a new page, numbered or not |
| Table | Rows from a repeating group, caption (numbered "Table 1"), which columns and in what order, text for no rows |
| Image | A file uploaded with the template or a technician's photo, caption (numbered "Figure 1"), width; at most about 40% of the page height |
| Callout | A named tone from the style (Info, Note, Warning, Critical, Success), or a custom colour; the text colour is picked for contrast and the builder warns below 4.5:1 |
| Sources | Sources every report gets, plus the technician's own; printed as a numbered list |
| Signatures | One to four boxes: who signs each, handwritten or stamp, label, side by side or stacked, signing date |

The builder uses svelte-dnd-action for dragging from a palette and reordering, with click-to-add for touch screens and keyboard users. Renaming a question's variable updates every block, rule and calculated value that uses it. The preview and the renderer share the page rules: a visible section set to start on a new page begins one, a page-break block forces one, a hidden section takes its blocks with it, and no rule leaves an empty page. The preview shows A4 pages and flags a page that runs over; exact pagination is left to the renderer, which flows long content onto more pages. ([The builder prototype](../spikes/builder-prototype/README.md) has the details.)

### Shared library

Variables (such as the service desk phone number), text snippets (reusable paragraphs) and data tables (keys and values for `lookup()`) that every template and report can use, as `{{vars.name}}`, `{{text.name}}` and `lookup("table", "key")`. A snippet may use variables but not other snippets. Technicians can insert snippets into long answers.

Report Designers and Technicians can add and change entries. Every change is versioned and written to the audit log, and Administrators can lock an entry. A report uses the current values until it is signed; the signed revision stores the values it used, so later edits never change a signed report.

### Logic and CEL

Rules combine a condition (comparisons, ranges, AND / OR / XOR / NOT, IF / ELSE IF / ELSE, SWITCH, regular expressions) with actions (show or hide questions, sections and pages; set values; replace text; apply styles). A visual rule builder writes the expressions in CEL, the Common Expression Language; power users can also edit them as text.

CEL has no general loops, no file or network access and no code execution. The server evaluates with Google's official engine (cel-expr-python); the browser uses cel-js for the live form and preview. Skjald adds a small function library to both: `xor`, `switch`, `re_match`, `re_replace`, `replace`, `sum`, `lookup` and date helpers. Regular expressions go only through `re_match` and `re_replace`, which use RE2 on both sides (linear time, identical syntax); the template validator rejects CEL's built-in `matches()` and expressions longer than 2,000 characters. Browser evaluation runs in a Web Worker with a time limit. A shared test file runs both engines in CI ([the expression-language spike](../spikes/expression-language/README.md) has the results).

### Versions and translation

Published template versions are frozen. Templates move between installs as `.skjald` files (a ZIP with manifest, questions, layout, rules, strings, styles and assets); imports are schema-validated and sanitised. To translate a template, copy it and edit its Strings view.

## Signing

Every report gets a PAdES signature with an RFC 3161 timestamp from an independent timestamp service and embedded revocation data, plus a visible signature block. Each template sets who signs: the company seal, the technician, or the technician followed by a reviewer. All signature fields, including the lock on the last one, are created before the first signature.

The visible part of each signature is set per signer in the template:

- **Handwritten** — the signer's own signature above their name, role and signing time. Each user sets it up once in their profile: drawn in the browser, uploaded as a scan, or generated from their name in a handwriting-style font. It is stored encrypted and used only after MFA.
- **Stamp** — a company stamp with company name, role, signing time and report number, in the company brand.

Appearances are small HTML templates rendered by the same renderer as the reports, so they use the brand fonts and colours and keep the PDF/A output valid.

Signing runs in a separate **signer** container that holds the keys; the web-facing app never does. Keys are stored encrypted under the master key, and a user's key is used only after that user passes MFA. Certificates come from Skjald's built-in signing CA or from a commercial document-signing certificate, through a CSR flow so private keys never leave the server. The signer reaches keys through one interface, so a PKCS#11 HSM backend can be added later.

### Checking a signed report

Any user can upload a PDF to check it, for example a report a customer sends back. The signer checks each signature and its timestamp, whether anything but later signatures and validation data was added after signing, whether the file is still PDF/A, and whether this exact file (by SHA-256) is a report Skjald issued. The upload goes through the usual upload checks (size limit, file type, virus scan), is checked and then discarded, and each check is logged. ([The signing spike](../spikes/pdf-signing/README.md) has the checker.)

## Delivery

| Method | Release |
| --- | --- |
| Download | 1.0 |
| Email attachment (SMTP relay or Microsoft 365) | 1.0 |
| Password-protected PDF | 1.0 |
| Secure link with access code, through Bifrost | 1.1 |

Raw data travels beside the report as a separate encrypted bundle.

The PDF/A original is never encrypted, because PDF/A does not allow it. Encrypting a signed PDF afterwards breaks every signature (shown in [the PDF signing spike](../spikes/pdf-signing/README.md)). So when a report enters signing and its template allows password-protected delivery, Skjald generates the delivery password, stores it encrypted with the customer key, and each signer signs both the original and an encrypted copy in one action.

### Bifrost, the delivery gateway

Bifrost is a separate, optional service on its own small VM or VPS. It is the only part of Skjald that faces the internet.

1. Skjald encrypts each delivery with a fresh key and pushes the ciphertext to Bifrost. Connections only go from Skjald to Bifrost, never the other way.
2. The decryption key travels in the link after the `#`, which browsers never send to a server, so Bifrost never sees it.
3. The recipient enters an access code that was sent separately. Bifrost stores only a hash of it.
4. The recipient's browser downloads the ciphertext and decrypts it locally.
5. Bifrost deletes the files when the link expires or is revoked; Skjald collects access events into its audit log.

## Security model

### Sign-in and sessions

- **Passwords** are hashed with Argon2id (RFC 9106's low-memory profile) after Unicode NFKC normalisation, so the same password typed on any keyboard matches. Administrators set the minimum length (default 12). There are no composition rules (upper case, digits, symbols): ASVS forbids them because they push people towards predictable patterns. A password may not contain the username or "skjald", and is checked against Have I Been Pwned's Pwned Passwords range API: only the first 5 characters of its SHA-1 leave the server, and replies are padded. The check is an admin setting, on by default; it needs outbound HTTPS to `api.pwnedpasswords.com`, so offline installs turn it off. If the service can't be reached, the password is neither accepted nor rejected.
- **Failures look alike.** A wrong password, an unknown username, a disabled or locked account all get the same answer in about the same time; an unknown username still runs a full password check. The reason goes to the audit log only, and a typed username that matches no account is never logged, because people type passwords into that field.
- **Lockout and throttling.** An account locks for a set time after a set number of failures in a row (defaults: 10 failures, 15 minutes); a success resets the count. Separately, an address with 30 failures in 15 minutes is refused for a while, so one machine can't try many usernames below each lockout.
- **Sessions** are server-side. The browser holds a random 256-bit token in a `__Host-` cookie (HttpOnly, Secure, SameSite=Strict, no expiry date, so it ends with the browser); the database holds only its SHA-256. Sessions end after an idle period (default 30 minutes) and at a maximum length however active (default 12 hours); both are admin settings. Signing out deletes the session, so a copied cookie stops working.
- **CSRF.** Every state-changing request must carry the session's CSRF token in a header; the token is an HMAC of the session token, so it needs no storage and dies with the session. Browsers' `Sec-Fetch-Site` header is checked as well, which also covers sign-in.
- **Second factor gate.** A password alone gives a session that can only finish signing in. Every route that touches data requires a session that has passed MFA, so a new route can't skip it by accident. Such a session can add a factor only to an account that has none yet (the first sign-in); otherwise someone holding only the password could add their own. Passing the second factor issues a new session token, so a token seen before that point is worthless.
- **Second factors.** Authenticator apps (TOTP: SHA-1, 6 digits, 30 seconds, one step of clock drift either way, each code accepted once); passkeys and hardware keys (WebAuthn, bound to the host name in `SKJALD_ADDRESS`, which must be a name, not an IP address; a key whose signature counter goes backwards is refused as a likely copy); and 10 recovery codes, shown once when the first factor is set up and kept only as salted hashes. Wrong codes count towards the same lockout as wrong passwords, and only a full sign-in resets the count, so someone with the password can't keep guessing codes a few at a time between sign-ins.
- **Client address.** The app takes the client's address from `X-Forwarded-For`, which is safe because only Caddy can reach the app and Caddy replaces that header for every client.
- **Keep transactions short.** A transaction holds the database's write lock (see Components), so password hashing, rendering and network calls happen outside one. Sign-in commits before the password check and re-reads the account afterwards.

### Keys

- **Master key** — 256 random bits in `/etc/skjald/master.key`, generated by the installer, outside the data folder and never included in backups. The file and its folder belong to the app container's own unprivileged user (UID 10001, which no one logs in as) with mode 0600, because the app reads the key itself and never runs as root. On the host, only root and the app can read it, and the app sees it through a read-only mount.
- **Database key** — opens the SQLCipher database (as a raw 256-bit key, so opening a connection costs no key stretching). The app generates it on first start and keeps it in the data folder wrapped by the master key, so it travels in backups but opens nothing without the master key.
- **Customer keys** — generated per customer; encrypt that customer's files, answers, contacts and secrets. Deleting a customer destroys its key, so its data is unreadable everywhere, old backups included.
- **Signing keys** — held by the signer, wrapped by the master key.
- **Backup key** — separate; encrypts backups. The app generates it during setup, so the recovery kit is complete from the start, and keeps it wrapped by the master key in the data folder. The wrapped copy travels inside the encrypted backups, so a restore needs the backup key from the recovery kit.

Keys are wrapped with AES-256-GCM, and each wrapped key is bound to what it is for (for example one customer's ID), so a wrapped key copied onto another customer's record will not open.

The setup wizard shows a recovery kit (master and backup keys) once. Without it, backups cannot be restored. Keeping the master key in a file protects stolen disks, backups and database copies, but not a running VM whose root account is compromised, so shell access to the VM must stay tightly limited.

### Audit log

Sign-ins, admin and permission changes, every view, download and export, secret reveals, signing, deliveries, key operations, backups and deletions are logged. Each entry carries the hash of the previous one, and the chain head is timestamped daily, so tampering shows.

- Entries are numbered without gaps. Each entry's SHA-256 covers its own contents and the previous entry's hash, so an edited or removed entry breaks the chain at that point, and a check names the first broken entry.
- An entry is written in the same database transaction as the action it records, so neither can exist without the other.
- The database itself refuses updates and deletes on the log table, so an application bug cannot rewrite history. Someone with the database key could remove that guard, but not without breaking the chain.
- Removing the newest entries leaves a valid but shorter chain. The daily RFC 3161 timestamp of the chain head is what catches that; it runs in the background worker.
- Entries never contain passwords, codes, session tokens or secret field values.

### Hardening

- The PDF renderer has no network, a read-only filesystem and CPU, memory and time limits.
- Containers run as non-root with no extra capabilities.
- Rich text and SVG are sanitised; the browser gets a strict Content-Security-Policy. Scripts, styles, fonts, images and connections are limited to Skjald's own origin; the frontend build writes the policy into each page with the hash of SvelteKit's one inline script, and Caddy adds `frame-ancestors 'none'`. The only inline style allowed is SvelteKit's screen-reader route announcer, by its exact hash (`'unsafe-hashes'`, not `'unsafe-inline'`); a test fails if a SvelteKit upgrade changes it. Fonts are bundled, and Vite never inlines assets as `data:` URLs.
- Browser tests (Playwright, `frontend/e2e/run.sh`) run against the real stack behind Caddy on every pull request, including passkeys through Chrome's virtual authenticator, and fail on any CSP violation.
- Secret fields are encrypted and masked by default. A technician can reveal one for 30 seconds after an MFA check, and every reveal is logged. In the PDF a secret is printed partly — at most a quarter of its characters and at most three at each end, with a fixed run of dots that hides its length — or left out, per field. The customer gets the full value from the technician, by phone, or through a secure link from release 1.1.
- Uploads are checked against an admin-managed file type blocklist (by extension and content) and scanned with ClamAV.

## Components

```mermaid
flowchart TB
    Team["Your team<br/>browser, internal network"] -->|HTTPS 443| Caddy
    subgraph VM["Skjald VM (Docker Compose)"]
        Caddy["Caddy<br/>the only open port"] --> App["App<br/>FastAPI"]
        App --> ClamAV
        App --> Data[("Encrypted data<br/>SQLCipher + files")]
        Worker["Worker<br/>rendering, imports, email, backups"] --> Data
        Worker --> Renderer["Renderer<br/>WeasyPrint, no network"]
        Worker --> Signer["Signer<br/>pyHanko, holds keys"]
    end
    VM -->|outbound only| Outside["Directory, mail, timestamps,<br/>feeds, backup targets"]
    VM -->|push, outbound only| Bifrost["Bifrost gateway<br/>DMZ or VPS"]
    Customer -->|link + access code| Bifrost
```

Caddy is the single front door: it is the only open port, obtains and renews HTTPS certificates, and applies security headers, upload limits and the admin IP allowlist before a request reaches the app. The app and worker exchange jobs through a table in the encrypted database, so no separate queue server is needed.

SQLite allows one writer at a time, so every transaction takes the write lock when it begins (`BEGIN IMMEDIATE`) rather than at its first write. Steps that read and then write — the audit chain, report numbers, claiming a job — can then never interleave or fail halfway. At 1–10 users the cost is negligible. Schema changes are Alembic migrations, applied by the app container before it starts serving. Migrations never rebuild a table (Alembic's batch mode): on SQLite with foreign keys on, dropping the old copy deletes every row that cascades from it, and a test upgrades a database holding data to check nothing is lost. Tables whose IDs appear in the audit log use `AUTOINCREMENT`, so an ID is never reused for a different user or session.

| Part | Choice |
| --- | --- |
| Frontend | SvelteKit + TypeScript, built to static files |
| Backend | Python, FastAPI, SQLAlchemy |
| Database | SQLite + SQLCipher |
| PDF rendering | WeasyPrint (PDF/A-3b) |
| Signing | pyHanko |
| Rich text | TipTap |
| Proxy | Caddy |
| Backups | restic |
| Virus scanning | ClamAV |

## Deployment

- **Install:** one command on Ubuntu Server LTS installs Docker Engine if needed, generates the master key, verifies the signed images and starts the stack. A web wizard then sets up the company, the break-glass administrator, the recovery kit, TLS, email and backups. A plain `docker-compose.yml` is also published.
- **Setup wizard.** Until setup is finished, every page leads to `/setup`, and every step needs the one-time setup token. The app prints a fresh token to its log each time it starts while setup is pending, and `docker compose exec app python -m app.setup` prints another; only someone with access to the VM can read it. It is 120 random bits, kept only as a hash, refused after 10 wrong tries per address in 15 minutes, and dead once setup is complete. The wizard names the company and shows the server address (passkeys are tied to it), reviews the security settings, creates the break-glass Administrator and has them set up a second factor, then shows the recovery kit (the master and backup keys, in base32) until it is confirmed as saved. After that, every setup step answers 410 Gone and the keys are never shown again. Interrupted setups resume where they stopped. TLS, email and the backup target join the wizard as those features are built.
- **Break-glass Administrator.** A local account that works when the directory is down. Every sign-in with it is flagged in the audit log (and, once email exists, mailed to all Administrators).
- **Updates:** automatic by default, inside an admin-set maintenance window: verify signatures, back up, migrate, health-check, roll back on failure. Manual mode is available. The updater runs on the host, not in a container, because an updater container would need the Docker socket.
- **Backups:** encrypted restic backups to local disk, SMB shares or S3-compatible storage, with a scheduled restore test.

## Repository layout

```
frontend/    SvelteKit app
backend/     FastAPI app and background worker
renderer/    PDF renderer service
signer/      signing service
bifrost/     delivery gateway
templates/   built-in templates
deploy/      installer, compose files, Caddyfile
docs/        documentation and brand assets
```

## Roadmap

| Step | Scope |
| --- | --- |
| Phase 0 | Repository, CI and signed builds; design tokens; spikes for the expression language (CEL chosen), PDF/A with several signatures, SQLCipher and the drag-and-drop builder |
| Phase 1 | Installer and setup wizard, local sign-in with MFA, roles and assignments, admin panel, customers and projects, keys, audit log, backups |
| Phase 2 | Template builder: tabs, field types, block settings, rules in CEL, shared library, styles and page designer, "Try it" preview, versions, template files |
| Phase 3 | Reports end to end: editor with checkout, uploads, review, rendering, signing, checking signed reports, delivery, archive, retention, three built-in templates |
| 1.0 | Release gate: one-command install, ASVS Level 2 test plan passes, restore test green, all built-in templates sign end to end |
| 1.1 | Bifrost secure links |
| 1.2 | Active Directory and Entra ID sign-in, API tokens with IP allowlists, webhooks |
| 1.3 | Importers and vulnerability data feeds, more built-in templates |
| 1.4 | HSM support, syslog / SIEM forwarding, custom fonts |
