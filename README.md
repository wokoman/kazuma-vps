# Kazuma VPS

Infrastructure-as-code for my Ubuntu 24.04 VPS using Ansible. It configures:

- Caddy as reverse proxy with automatic HTTPS
- Static website built with Ark and deployed to `/var/www/site`
- Miniflux (RSS reader) installed from apt + PostgreSQL
- Video site for hosting annual video compilations

The VPS is managed directly with Ansible (no Kubernetes/ArgoCD).

## Structure

- `ansible.cfg` — Ansible config (includes SOPS integration)
- `ansible/inventory/hosts.yml` — Inventory file (unencrypted, references vars)
- `ansible/inventory/group_vars/all.sops.yml` — Variables (SOPS-encrypted)
- `ansible/playbooks/site.yml` — Main playbook
- Roles:
  - `provision_user` — Creates `ansible` user with SSH key + NOPASSWD sudo
  - `common` — Base packages + UFW firewall (HTTP/HTTPS)
  - `security_hardening` — SSH hardening (custom port, disable root), fail2ban
  - `ark_build` — Builds Ark site locally (via venv) and deploys output
  - `website` — Static files deploy (used if Ark disabled)
  - `1se_site` — 1SE video site (HTML player + videos directory)
  - `miniflux` — Postgres + Miniflux apt package + config
  - `caddy` — Installs and configures Caddy + vhosts
- `static-sites/ark/` — Ark project (source)
- `static-sites/1se/` — 1SE video site (HTML only, videos uploaded separately)

## Prerequisites

- Ansible installed locally
- SOPS installed (`brew install sops` on macOS)
- AGE encryption key at `~/Library/Application Support/sops/age/keys.txt` (macOS)
- Ansible collection: `ansible-galaxy collection install community.sops`

## Bootstrap from Clean Machine

If you have a **fresh Ubuntu 24.04 VPS** with only root access:

1. **Initial setup** — Connect as root or your personal user to create the `ansible` user:
   ```bash
   # Connect with your initial user (e.g., root or michalkozak)
   ansible-playbook ansible/playbooks/site.yml -u root --become
   
   # Or if you have a personal user already:
   ansible-playbook ansible/playbooks/site.yml -u michalkozak --become
   ```

2. **What this does automatically:**
   - Creates `ansible` user with your SSH key and NOPASSWD sudo
   - Configures SSH: custom port (non-standard), disables root login, disables password auth
   - Sets up UFW firewall: allows custom SSH port, 80 (HTTP), 443 (HTTPS)
   - Installs and configures fail2ban for SSH protection
   - Installs Caddy, Miniflux, and deploys your website

3. **After first run** — SSH will be on a custom port, use the `ansible` user:
   ```bash
   ansible-playbook ansible/playbooks/site.yml --become
   ```
   
   The inventory is configured to use the custom SSH port automatically via encrypted variables.

## Quick Start (Existing Setup)

**Deploy changes to existing infrastructure:**

```bash
ansible-playbook ansible/playbooks/site.yml --become
```

**DNS Configuration**

Point these DNS records to your VPS IP:
- `michalkozak.cz` → A record
- `miniflux.michalkozak.cz` → A record
- Two subdomains for the video site 🤠
- Optional: `www.michalkozak.cz` → A record (Caddy redirects to apex)

**Deploy website changes only:**

- Ark build + deploy:
  ```bash
  ansible-playbook ansible/playbooks/site.yml --become --tags website
  ```
- Plain static (if Ark disabled):
  - Put files into `website/` and run the same `--tags website`

**Tip:** To update your CV PDF, replace `static-sites/ark/res/CV_en.pdf` and redeploy with `--tags website`.

**Notes:**
- Ark tasks run locally using a venv under `.venv/ark`.
- In check mode (`--check`) the Ark build is skipped to avoid local-path issues.

## Local Development with Ark

The main website uses [Ark](https://www.dmulholl.com/docs/ark/master/) static site generator. To develop locally:

**Setup (first time only):**
```bash
# Create virtual environment and install Ark
python3 -m venv .venv/ark
.venv/ark/bin/pip install ark==7.7.0
```

**Local development:**
```bash
cd static-sites/ark

# Build the site
../../.venv/ark/bin/ark build

# Run local dev server (http://localhost:8080)
../../.venv/ark/bin/ark serve

# Or watch for changes and auto-rebuild
../../.venv/ark/bin/ark watch
```

The site source is in `static-sites/ark/src/`, templates in `static-sites/ark/lib/graphite/templates/`.

## 1SE Video Site

The 1SE (One Second Every Day) video site hosts annual video compilations.

### How It Works

- Simple HTML5 video player with JavaScript for year selection
- Videos are stored on the VPS at `/var/www/1se/videos/`
- Access logs at `/var/log/caddy/1se-access.log` for monitoring traffic spikes
- Site is unlisted (`noindex, nofollow`) - only accessible via direct link

### Deploy 1SE Site Changes

If you modify `static-sites/1se/index.html`:

```bash
ansible-playbook ansible/playbooks/site.yml --tags 1se --become
```

### Adding a New Year's Video

When a new annual video is ready:

1. **Update the HTML** — Edit `static-sites/1se/index.html` and add the new year to the `videos` array:
   ```javascript
   const videos = [
       { year: 2026, file: '1SE 2026.mp4' },  // Add new year at top
       { year: 2025, file: '1SE 2025.mp4' },
       // ... rest of years
   ];
   ```

2. **Deploy the updated HTML:**
   ```bash
   ansible-playbook ansible/playbooks/site.yml --tags 1se --become
   ```

3. **Upload the new video:**
   ```bash
   rsync -avz --progress -e "ssh -p {{ port }}" \
     "/path/to/1SE 2026.mp4" \
     {{ ose_site_upload_user }}@{{ host }}:/var/www/1se/videos/
   ```

### Monitoring Access

Check access logs for unusual traffic (bot scraping, etc.):

```bash
# Live tail
tail -f /var/log/caddy/1se-access.log

# Top requested URLs
cat /var/log/caddy/1se-access.log | jq -r '.request.uri' | sort | uniq -c | sort -rn | head -20
```

## Miniflux

Miniflux is installed from the upstream `.deb` on GitHub, not Ubuntu universe — the Ubuntu
package is frozen at 2.0.51 for the life of 24.04. Upstream's APT repo publishes no
`Release` file, so consuming it would mean `[trusted=yes]` and no signature checking at
all; a release `.deb` verified against a pinned SHA-256 is the safer trade. Version and
checksum live in `ansible/roles/miniflux/defaults/main.yml`, and the package is
`apt-mark hold`-ed so `apt upgrade` can never move it.

### Upgrading

Miniflux runs its schema migrations on start (`RUN_MIGRATIONS=1`) and they are one-way.

1. Read the [release notes](https://github.com/miniflux/v2/releases) for every version you're skipping.
2. Back up and verify the backup restores:
   ```bash
   ansible web -m shell -a "sudo -u postgres pg_dump miniflux > /root/miniflux-$(date +%F).sql" --become
   ansible web -m shell -a "sudo -u postgres psql -c 'create database miniflux_restoretest'" --become
   ansible web -m shell -a "sudo -u postgres psql miniflux_restoretest < /root/miniflux-$(date +%F).sql" --become
   ansible web -m shell -a "sudo -u postgres psql -c 'drop database miniflux_restoretest'" --become
   ```
3. Bump `miniflux_version` and `miniflux_checksum` (the release page has no `.deb`
   checksum file, so hash it yourself: `shasum -a 256 miniflux_<ver>_amd64.deb`), then
   deploy:
   ```bash
   ansible-playbook ansible/playbooks/site.yml --become --tags miniflux --check --diff
   ansible-playbook ansible/playbooks/site.yml --become --tags miniflux
   ```
4. Verify: `curl -i http://127.0.0.1:8080/` on the host serves the sign-in page (since
   2.3.x `/login` is POST-only and answers `405` to a `GET`), then log in.

Known upgrade traps: 2.2.18 blocks feeds and integrations on private networks unless
`FETCHER_ALLOW_PRIVATE_NETWORKS=1` / `INTEGRATION_ALLOW_PRIVATE_NETWORKS=1` are set, and
2.2.17 removed `FILTER_ENTRY_MAX_AGE_DAYS` in favour of a `max-age:` filter rule.

## Security & Secrets Management

### SOPS Encryption

Sensitive variables are encrypted with [SOPS](https://github.com/getsops/sops) using AGE encryption:
- `ansible/inventory/group_vars/all.sops.yml` — Contains passwords, domains, connection details, API keys

The `community.sops` Ansible collection automatically decrypts `.sops.yml` files in `group_vars/` and `host_vars/` directories during playbook execution.

### Initial Setup

The repository is configured with:
- `.sops.yaml` — Defines the AGE public key for encryption
- `ansible.cfg` — Enables `community.sops.sops` vars plugin and points to your AGE key file

### Working with Encrypted Files

**To view or edit encrypted variables:**
```bash
# Opens in $EDITOR, auto-decrypts and re-encrypts on save
sops ansible/inventory/group_vars/all.sops.yml
```

When running Ansible playbooks, the `community.sops` plugin automatically decrypts `*.sops.yml` files.

### AGE Key Management

**AGE key locations:**
- **Public key** (in `.sops.yaml`): `age1nl58z4scpayqter2xldkcc0cyz06vel75m2kz6nlpxuqw8jmqfaqxepwa6`
- **Private key** (configured in `ansible.cfg`): `~/Library/Application Support/sops/age/keys.txt`

**On Linux/other systems**, the default location is `~/.config/sops/age/keys.txt`

**If you need to regenerate the AGE key pair:**
```bash
# Install age if not already installed
brew install age

# Generate new key pair
age-keygen -o ~/.config/sops/age/keys.txt

# Update .sops.yaml with the new public key (shown in output)
# Re-encrypt all files with new key
sops updatekeys ansible/inventory/group_vars/all.sops.yml
```

## Troubleshooting

### General

- Caddy logs: `journalctl -u caddy -f`
- Miniflux logs: `journalctl -u miniflux -f`
- Verify Miniflux locally: `curl -i http://127.0.0.1:8080/login`
- UFW rules: `sudo ufw status numbered`

### 1SE Video Site

- Check if videos are accessible: `curl -I https://{{ host }}/videos/1SE%202024.mp4`
- View access logs: `tail -20 /var/log/caddy/1se-access.log`

## Security Hardening

### Automated Security Features

All security hardening is **fully automated** via the `security_hardening` Ansible role:

- Secrets encrypted with SOPS (AGE) - All sensitive data encrypted at rest
- SSH key authentication only - Password authentication disabled
- Custom SSH port - Automatically configured to non-standard port
- Root SSH login disabled - Direct root login not permitted
- Dedicated `ansible` user - NOPASSWD sudo for automation only
- UFW firewall active - Allows only custom SSH port, 80 (HTTP), 443 (HTTPS)
- Fail2ban active - SSH brute-force protection (1h ban after 5 failures in 10min)
- Automatic HTTPS - Caddy with Let's Encrypt certificates

**Check fail2ban status:**
```bash
ansible web -m shell -a "fail2ban-client status sshd" --become
```

**View current UFW rules:**
```bash
ansible web -m shell -a "ufw status numbered" --become
```

## Development Workflow

1. **Make changes to encrypted variables:**
   ```bash
   sops ansible/inventory/group_vars/all.sops.yml
   ```

2. **Test playbook:**
   ```bash
   ansible-playbook ansible/playbooks/site.yml --check --diff
   ```

3. **Deploy:**
   ```bash
   ansible-playbook ansible/playbooks/site.yml --become
   ```

4. **Deploy specific components only:**
   ```bash
   # Security hardening only
   ansible-playbook ansible/playbooks/site.yml --tags security --become
   
   # Website updates only
   ansible-playbook ansible/playbooks/site.yml --tags website --become
   
   # 1SE video site only
   ansible-playbook ansible/playbooks/site.yml --tags 1se --become
   
   # Miniflux only
   ansible-playbook ansible/playbooks/site.yml --tags miniflux --become
   
   # Caddy configuration only
   ansible-playbook ansible/playbooks/site.yml --tags caddy --become
   ```

5. **Commit encrypted files:**
   ```bash
   git add ansible/inventory/group_vars/all.sops.yml
   git commit -m "Update configuration"
   git push
   ```

## Migration to New VPS

To migrate to a new clean VPS:

1. Update `vps_ansible_host` in encrypted `group_vars/all.sops.yml` with new IP
2. Update DNS records to point to new IP
3. Run the bootstrap command as root/initial user on new VPS
4. Everything will be automatically configured identically
5. Re-upload 1SE videos using the rsync command above

## Backups & Recovery

Every night at 01:00 the VPS writes `/var/backups/vps/vps-<UTC>.tar.age`, keeping the
last two. At 01:30 the NAS (`dwight`) pulls them over the tailnet into
`/volume1/homes/michalkozak/Zálohy/kazuma`, and the existing offsite Hyper Backup job
ships that at 02:00.

An archive contains `databases/<name>.dump` (Postgres custom format) and the
configuration paths listed in `backup_paths`. Videos under `/var/www/1se` are
deliberately excluded — the NAS holds the masters.

Archives are encrypted to the same age recipient as SOPS. **The private key in
1Password is the only thing that can read them.** Without it the backups are noise.

### Restore drill

Run this roughly monthly, and after changing anything in the `backup` role. It is
non-destructive: nothing touches live data.

```bash
# 1. Newest archive from the NAS (adjust the path if you run it on the NAS itself)
scp "dwight:/volume1/homes/michalkozak/Zálohy/kazuma/$(ssh dwight 'ls -1 "/volume1/homes/michalkozak/Zálohy/kazuma" | tail -1')" /tmp/

# 2. Decrypt and unpack with nothing but the age key — this is the step that matters
mkdir -p /tmp/drill
age -d -i "$HOME/Library/Application Support/sops/age/keys.txt" /tmp/vps-*.tar.age \
  | tar -xzf - -C /tmp/drill
find /tmp/drill -type f

# 3. Prove the dumps actually restore, into a scratch database on the VPS
for db in forgejo miniflux; do
  ansible web -m copy -a "src=/tmp/drill/databases/$db.dump dest=/tmp/drill.dump" --become
  ansible web -m shell -a 'sudo -u postgres createdb drill_test \
    && sudo -u postgres pg_restore -d drill_test /tmp/drill.dump \
    && sudo -u postgres psql -Atd drill_test \
         -c "select count(*) from information_schema.tables where table_schema='"'"'public'"'"'" \
    && sudo -u postgres dropdb drill_test && rm /tmp/drill.dump' --become
done

# 4. Clean up the plaintext copies
rm -rf /tmp/drill /tmp/vps-*.tar.age
```

A non-zero table count for each database in step 3 means the chain works end to end: the timer ran, the
NAS pulled a current archive, your key decrypts it, and the dump loads. Anything less
than that is an untested backup.

### Rebuilding the VPS from scratch

1. Provision Ubuntu 24.04 and repoint DNS. Do DNS first — Caddy needs it to issue
   certificates, and TLS material is not backed up (it is re-issued, not restored).
2. **Generate a fresh Tailscale auth key.** The one in SOPS is single-use and already
   consumed, so it cannot enroll a second machine. Update `tailscale_auth_key`.
3. Run the bootstrap flow above, which recreates users, databases, and services empty.
4. Restore data from a single archive — never mix archives, since a database and the
   repository or config data it references are only consistent within one:
   ```bash
   age -d -i "$HOME/Library/Application Support/sops/age/keys.txt" vps-<ts>.tar.age \
     | tar -xzf - -C /tmp/restore
   # per database: drop what the playbook created, then load the dump
   sudo -u postgres dropdb <name> && sudo -u postgres createdb -O <owner> <name>
   sudo -u postgres pg_restore -d <name> /tmp/restore/databases/<name>.dump
   # then copy back the configuration paths and restart the services
   ```
5. Log in to each service and confirm real data is present before deleting anything.

## Forgejo

Self-hosted git at `git.michalkozak.cz`. Single static binary from Codeberg pinned by
version and SHA256 in `ansible/roles/forgejo/defaults/main.yml`, running as the `git`
user behind Caddy. Registration is disabled, there is no mailer, and Actions and LFS are
off — the box has ~3 GB spare disk (see `PLAN-forgejo.md`).

`SECRET_KEY`, `INTERNAL_TOKEN` and `oauth2.JWT_SECRET` are generated once into
`/etc/forgejo/` and referenced from `app.ini` by `*_URI`, so re-running the playbook
never rotates them. Losing `secret_key` makes stored 2FA secrets undecryptable, which is
why `/etc/forgejo` is in `backup_paths`.

Clone URLs use Forgejo's own SSH server, leaving the host's hardened sshd untouched:

```bash
git clone ssh://git@git.michalkozak.cz:2222/<owner>/<repo>.git
```

### Creating the first account

Registration is disabled, so the admin account is made on the host:

```bash
ansible web -m shell -a 'sudo -u git env GITEA_WORK_DIR=/var/lib/forgejo \
  /usr/local/bin/forgejo admin user create --admin --username <name> \
  --email <email> --random-password --config /etc/forgejo/app.ini' --become
```

Store the printed password in 1Password, then enable TOTP in the web UI and store the
recovery codes too. With no mailer there is no password reset by email — use
`forgejo admin user change-password` on the host instead.

### Upgrading

Migrations run on start and are one-way, so back up first and read the release notes.
Subscribe Miniflux to the Forgejo release feed; that is the upgrade trigger.

```bash
# find the checksum for the version you want
curl -sL https://codeberg.org/forgejo/forgejo/releases/download/v<X.Y.Z>/forgejo-<X.Y.Z>-linux-amd64.sha256

# bump forgejo_version and forgejo_checksum, then
ansible-playbook ansible/playbooks/site.yml --become --tags forgejo
```
