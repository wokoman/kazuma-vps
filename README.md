# Kazuma VPS

Infrastructure-as-code for my Ubuntu 24.04 VPS using Ansible. It configures:

- Caddy as reverse proxy with automatic HTTPS
- Static website built with Ark and deployed to `/var/www/site`
- Miniflux (RSS reader) installed from apt + PostgreSQL

The VPS is managed directly with Ansible (no Kubernetes/ArgoCD).

## Structure

- `ansible/ansible.cfg` — Ansible config
- `ansible/playbooks/site.yml` — Main playbook
- Roles:
  - `provision_user` — Creates `ansible` user with SSH key + NOPASSWD sudo
  - `common` — Base packages + UFW allow 22/80/443
  - `ark_build` — Builds Ark site locally (via venv) and deploys output
  - `website` — Static files deploy (used if Ark disabled)
  - `miniflux` — Postgres + Miniflux apt package + config
  - `caddy` — Installs and configures Caddy + vhosts
- `static-sites/ark/` — Ark project (source)

## Quick Start

1) First run (provision user if needed)

If connecting as your own user initially:

```
ansible-playbook ansible/playbooks/site.yml -u michalkozak --become
```

Subsequent runs (use `ansible` user):

```
ansible-playbook ansible/playbooks/site.yml --become
```

2) DNS

- `michalkozak.cz` → A to your VPS IP
- `miniflux.michalkozak.cz` → A to your VPS IP
- Optional: `www.michalkozak.cz` → A to your VPS IP (Caddy redirects to apex)

3) Deploy website changes

- Ark build + deploy:
  - `ansible-playbook ansible/playbooks/site.yml --become --tags website`
- Plain static (if Ark disabled):
  - Put files into `website/` and run the same `--tags website`

Tip: To update your CV PDF, replace `static-sites/ark/res/CV_en.pdf` and redeploy with `--tags website`.

Notes:
- Ark tasks run locally using a venv under `ansible/.venv/ark`.
- In check mode (`--check`) the Ark build is skipped to avoid local-path issues.

## Troubleshooting

- Caddy logs: `journalctl -u caddy -f`
- Miniflux logs: `journalctl -u miniflux -f`
- Verify Miniflux locally: `curl -i http://127.0.0.1:8080/login`
- UFW rules: `sudo ufw status numbered`

## Security/Hardening

- SSH remains on port 22 (change manually if desired and set `ansible_port` in `hosts.ini`).
- Consider disabling SSH password auth and root login after initial provisioning.
- Consider SOPS‑encrypting `ansible/inventory/group_vars/all.yml` for secrets.


## Ansible for VPS

For a non-Kubernetes VPS setup (Ubuntu 24.04) using Ansible with Caddy, static site, and optional Miniflux, see `README-ANSIBLE.md`.
