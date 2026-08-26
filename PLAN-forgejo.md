# Plan: Forgejo on the VPS (+ backups)

Outcome of a design session on 2026-08-26. Two projects, not one: the `backup`
role is worth doing on its own merits and comes first.

## Constraints (measured 2026-08-26)

- Disk: 20 G total, 3.0 G free (84% used). `/var/www/1se` is 12 G of it.
- RAM: 961 MB total, ~622 MB available. 1 vCPU.
- No Docker on the box; everything is apt/binary + systemd + Caddy.
- Consequence: **no LFS, no Actions runner** until the video offload or a
  bigger instance. ironpod's `.git` is 3 MB, so it costs nothing.

## Decisions

**Role of the instance.** A third place — private-ish repos and things that
don't belong on GitHub. Not primary origin, not a mirror. `kazuma-vps` and
anything public-facing stays on GitHub.

**Forgejo.** Native binary (no apt repo exists), pinned version + SHA256 via
`get_url`, `/usr/local/bin/forgejo`, systemd, `RUN_USER=git` as a dedicated
system user. Postgres (own DB/role beside Miniflux). Registration disabled,
no mailer (password reset via `forgejo admin user change-password`), TOTP on
the admin account. Public at `git.michalkozak.cz`, Caddy vhost with
`X-Robots-Tag: noindex`. Built-in SSH on 2222, UFW + fail2ban jail.

`SECRET_KEY` and `INTERNAL_TOKEN` are generated once and stored in
`all.sops.yml`. Re-rendering them on every run silently invalidates sessions,
2FA, and stored secrets.

Upgrades: pinned, bumped by hand. Forgejo's release feed goes into Miniflux —
that's the trigger. Never track latest: migrations are one-way.

**Backups.** A `backup` role covering the box, not a Forgejo script.
Nightly `pg_dump` (Forgejo + Miniflux) plus `/var/lib/forgejo` and
`/etc/caddy`, age-encrypted, timestamped filenames, last 2 kept locally,
aborts if free space < 500 MB. `/var/www/1se` excluded — already on the NAS.

Tailnet policy uses the `grants` syntax: `tag:server` is owned by
`autogroup:admin`, and the default allow-all grant is narrowed from `*` to
`autogroup:member`. Tagged devices are not members, so the VPS gets no
tailnet access by default while member-owned devices keep theirs. Tagged
nodes also never expire their node key. The auth key stored in SOPS does
expire after 90 days, which only matters when rebuilding the VPS from
scratch — generate a fresh one then.

The NAS **pulls**, over Tailscale. The VPS is the internet-facing box, so it
holds no credential that can reach home. `dwight` is untagged, so its node
key expiry must be disabled by hand — an expired key would stop backups
silently.

Timings chain into the existing offsite job: VPS dumps at 01:00, the NAS
pulls at 01:30, and Hyper Backup ships it offsite at 02:00. Scheduling the
pull after 02:00 would leave the offsite copy a day stale.

DSM notifies on task failure. That only catches a failed pull, so the VPS
writes timestamped files and deletes partials on error, and the NAS task
fails if the newest file is older than 48 h — otherwise a broken `pg_dump`
means the NAS re-copies a stale tarball and reports success forever.

The age recovery key must live somewhere that is not the VPS.

## Phase 1 - backup role

1. **Tailscale on the VPS.** apt repo, auth key from SOPS,
   `--advertise-tags=tag:server`.
   *Verify:* NAS can ssh the VPS over its tailnet IP; node shows no expiry.
2. **Dump script + timer.** Python at `/usr/local/bin/vps-backup`, systemd
   service + nightly timer, writing `/var/backups/vps-<ts>.tar.age`.
   *Verify:* manual run produces a fresh file; the free-space guard trips at
   a faked threshold; `age -d` yields a readable tar.
3. **Age recovery key off-box** — password manager + NAS.
   *Verify:* decrypt a backup on the Mac using only the recovery key.
4. **NAS pull task.** DSM scheduled task over the tailnet, 48 h freshness
   assertion, notifications on failure.
   *Verify:* backdate a file and confirm DSM actually alerts.

## Phase 2 - Forgejo

5. **DNS** — `git.michalkozak.cz` A record. Early; cert issuance needs it.
   *Verify:* `dig +short git.michalkozak.cz`.
6. **`forgejo` role.** As decided above.
   *Verify:* `systemctl is-active forgejo`; `curl 127.0.0.1:3000` serves the
   UI; a second playbook run leaves `app.ini` unchanged and the session live.
7. **UFW + fail2ban.** Open 2222, jail on Forgejo's SSH log.
   *Verify:* clone over `ssh://git@git.michalkozak.cz:2222/...`;
   `fail2ban-client status forgejo`. Done — the jail bans at maxretry on
   Forgejo's `[W] Failed authentication attempt ... from <ip>` line. Only web
   logins produce it; failed API basic-auth logs a bare 401 the filter misses.
8. **Caddy vhost.** Reverse proxy to `127.0.0.1:3000`, `noindex` header.
   *Verify:* HTTPS with a valid cert, header present.
9. **Admin account + TOTP**, seed and recovery codes in the password manager.
   *Verify:* log out, log back in with TOTP.
10. **Forgejo release feed into Miniflux.**

## Phase 3 - migrate and prove

11. **ironpod** from `code.nolog.cz` via Forgejo's migration tool, not
    `git push --mirror` — it has issues #1-11 and a PR that a mirror drops.
    Repoint `origin`, then delete the source.
    *Verify:* issue and PR counts match before deleting anything.
    Done, and widened: `dochazkotron-5000` off nolog too, `dotfiles` and
    `docker-quake3-osp-server` off GitHub. quake3 keeps its GitHub copy as a
    Forgejo push mirror. `kazuma-vps` deliberately stays on GitHub — hosting
    the VPS's own rebuild instructions on that VPS is circular.
12. **Restore drill, ~4 weeks out.** Pull from the NAS, restore to a scratch
    dir, confirm the DB and repo data are coherent. Until this passes the
    backup is a belief, not a backup.

## Parked

- Moving the 12 G of video off `/var/www/1se`: Caddy proxies `/videos/*` to
  the Synology over the tailnet. Decided over object storage because home
  upload is 500 Mbit against ~30 views a year, so bandwidth is a non-issue
  and there is no recurring cost. Accepts that the VPS then reaches into the
  home network, so the ACL grants `tag:server` the single video port only,
  the share is read-only, and backups stay NAS-pull. Unblocks Actions and LFS.
- Forgejo Actions runner. Blocked on the above.
