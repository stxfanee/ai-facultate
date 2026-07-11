# Deployment

For public sharing, use HTTPS through Cloudflare Tunnel or Tailscale Funnel.

Do not expose raw router ports.

## Cloudflare Tunnel

Recommended for friends who should not install Tailscale. The tunnel exposes Streamlit on port `8501` through an HTTPS URL.

## Tailscale Funnel

Useful when Tailscale is already configured and Funnel is available on the account.

## Authentication warning

No-password profiles are acceptable for local/LAN/Tailscale testing. Public Internet deployment should enable real authentication before wider sharing.
