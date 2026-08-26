# Plan: serve the 1SE videos from the NAS

Outcome of a design session on 2026-08-26. The disk on the VPS is the binding
constraint on everything else (Actions, LFS), and 12 G of it is video that
already lives at home.

## Measured (2026-08-26)

- Disk: 20 G total, 2.7 G free (86% used). `/var/www/1se/videos` is 12 G in
  14 files, of which **13 are referenced by `index.html`**.
- `1SE 2025.mp4`: h264, 3840x2160, 30 fps, 20.8 Mbps, 6:24.
- Access log, 31 Jan - 26 Aug: 29.8 GB served, 1083 unique IPs. Split by
  bytes pulled: **13 IPs over 50 MB** (the actual audience, Czech residential
  ISPs), 24 between 1 and 50 MB, **1046 under 1 MB** - `l9scan`,
  `CensysInspect` and headless Chrome that never touch a video. They find the
  host through Certificate Transparency logs, which publish every hostname
  Caddy gets a cert for.
- Home connection: 1000/500 Mbit. Bandwidth is not a constraint.

## Decisions

**Move all 13 videos; the VPS keeps only `index.html`.** The disk is the
obvious reason, but the better one is the yearly workflow: adding a year
becomes "save the file at home", instead of rsyncing 1.3 G over the internet
to a box that is 86% full.

**No re-encode.** 20.8 Mbps is a normal 4K H.264 rate, not a bloated export -
the file sizes are explained by resolution, not by careless encoding. HEVC or
AV1 would roughly halve it, but Firefox plays neither reliably, and this page
gets sent to family.

**No object storage.** MinIO is not in Synology's Package Center - it means
SynoCommunity or a container. Browsers speak HTTP, not S3, so every request
would still terminate at Caddy as plain HTTP; the bucket layer would serve no
one.

**Web Station**, the official DSM package, nginx underneath, pointed at one
folder, on a non-standard port reachable only over the tailnet.

**The trust direction is deliberately reversed.** The backup design holds no
VPS credential that can reach home - the NAS pulls. This inverts that for one
port. A new tailnet grant lets `tag:server` reach `dwight` on the Web Station
port only; the VPS still cannot ssh the NAS. A compromised VPS would gain
read access to files that are already public on that same VPS, so the
marginal exposure is zero. Nothing else is loosened.

**Copy, not move.** Hyper Backup's source set is `homes` plus `Music`, so the
originals stay covered where they are. The copy under `/volume1/web/1se` is
derived data and needs no backup of its own. The cost is that a new year has
to land in both places - written into the workflow so it is not discovered
later.

**Failure is visible and in two languages.** When the NAS is unreachable
Caddy answers with a short Czech and English page, not `502 Bad Gateway`.

**Logging matches how the logs are actually used** - not read routinely, only
when something looks wrong. The apex, Miniflux and Forgejo keep bare `log`
into journald, which the maintenance role already caps. `log_skip` drops
scanner bait everywhere, and the 1SE file log narrows to `/videos/`
requests, turning 14,000 lines of Censys into roughly 30 lines a month of
real viewers.

## Phase 0 - quick win

1. **Delete the stray.** `/var/www/1se/videos/1SE`, 1.3 G, no extension, not
   a copy of any other file, referenced by nothing.
   *Verify:* 1.3 G freed; the page still lists all 13 years and each plays.

## Phase 1 - NAS side (manual; DSM is outside Ansible)

2. **Create `/volume1/web/1se` and copy the 13 videos in.**
   *Verify:* `ls -la` byte counts match the VPS originals exactly.
3. **Web Station**: install, create a web service pointing at that folder,
   assign a non-standard port, directory listing off.
   *Verify:* from another tailnet device,
   `curl -I 'http://dwight:<port>/1SE%202025.mp4'` returns 200 with
   `Accept-Ranges: bytes` - without ranges, seeking in the player breaks.
4. **Tailnet grant**: `tag:server` to `dwight` on that port only.
   *Verify:* the VPS can `curl` the video; the VPS still cannot ssh the NAS.

## Phase 2 - VPS side (Ansible)

5. **Caddy vhost**: `reverse_proxy` `/videos/*` to the NAS origin, bilingual
   `handle_errors` page, `log_skip` for scanner paths, file log narrowed to
   `/videos/`. Confirm `encode` is not trying to compress `video/mp4` - on
   1 vCPU that would be pure waste.
   *Verify:* a video plays end to end in a browser and seeking works; stop
   Web Station and the friendly page appears instead of a 502.
6. **Delete `/var/www/1se/videos`.** Only after step 5 is confirmed working.
   *Verify:* `df` shows roughly 26% used; every year still plays.

## Phase 3 - documentation

7. **README**: rewrite "Adding a New Year's Video" - copy to the NAS folder
   and to `homes`, update `index.html`, deploy. The rsync-to-VPS instruction
   is gone. Record the Web Station port and the tailnet grant so a NAS
   rebuild is reproducible.

## Outcome (2026-08-26)

Done. Disk went from 86% to 24% (2.7 G free to 14 G). Videos stream from the
NAS with working range requests, verified in Waterfox on both the oldest and
the largest file.

Two things the build changed beyond the plan:

- Caddy is now **reloaded, not restarted**, and the Caddyfile is validated
  before it is written. A restart severs in-flight downloads, which matters a
  great deal more now that every video is a proxied gigabyte.
- Upstream 4xx/5xx are re-raised as Caddy's own errors. Without that, a
  missing video handed visitors Synology's branded error page. Note that
  `error {rp.status_code}` does **not** work - Caddy reads the placeholder as
  a message and returns 500 - so the statuses are mapped explicitly.

`encode` needed no change: it already declines to compress `video/mp4`,
confirmed by measurement rather than assumption.

The hourly NAS uptime check gained a range request against a video, because
this migration created a failure mode where every site answers 200 while no
video plays.
