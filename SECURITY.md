# Security policy

## Supported version

This repository is under active early development. Security fixes are applied to the `main` branch.

## Reporting a vulnerability

Please do not open a public issue for sensitive security problems. Contact the maintainer privately or open a minimal issue asking for a secure contact path.

## Public deployment notes

- Use Cloudflare Tunnel or Tailscale Funnel instead of router port forwarding.
- Keep no-password profiles limited to local, LAN or trusted testing.
- Enable real authentication before sharing a public URL broadly.
- Never commit `.env` files, tunnel credentials, SQLite runtime data, uploaded documents or model files.
