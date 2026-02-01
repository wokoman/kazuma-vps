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
