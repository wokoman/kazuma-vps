# Kazuma VPS

Infrastructure-as-code for my Ubuntu 24.04 VPS using Ansible. It configures:

- Caddy as reverse proxy with automatic HTTPS
- Static website built with Ark and deployed to `/var/www/site`
- Miniflux (RSS reader) installed from apt + PostgreSQL

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
  - `miniflux` — Postgres + Miniflux apt package + config
  - `caddy` — Installs and configures Caddy + vhosts
- `static-sites/ark/` — Ark project (source)

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
- Ark tasks run locally using a venv under `ansible/.venv/ark`.
- In check mode (`--check`) the Ark build is skipped to avoid local-path issues.

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

## Security Hardening

### Automated Security Features

All security hardening is **fully automated** via the `security_hardening` Ansible role:

- ✅ **Secrets encrypted with SOPS (AGE)** - All sensitive data encrypted at rest
- ✅ **SSH key authentication only** - Password authentication disabled
- ✅ **Custom SSH port** - Automatically configured to non-standard port
- ✅ **Root SSH login disabled** - Direct root login not permitted
- ✅ **Dedicated `ansible` user** - NOPASSWD sudo for automation only
- ✅ **UFW firewall active** - Allows only custom SSH port, 80 (HTTP), 443 (HTTPS)
- ✅ **Fail2ban active** - SSH brute-force protection (1h ban after 5 failures in 10min)
- ✅ **Automatic HTTPS** - Caddy with Let's Encrypt certificates

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
   
   # Miniflux only
   ansible-playbook ansible/playbooks/site.yml --tags miniflux --become
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
