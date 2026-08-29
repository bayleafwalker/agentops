#!/usr/bin/env bash
# Single indirection point for "where does a forge credential come from".
#
# THIS IS THE LAYER SEAM. Today it reports the direct credential stores. When
# cred-broker's remote client lands, only this file changes -- the hooks, gates,
# vocabulary and allowlists above it are broker-agnostic.
#
# Prints STATUS ONLY. It must never print a secret value.
set -uo pipefail
case "${1:-status}" in
  status)
    printf 'github: '
    if gh auth status >/dev/null 2>&1; then
      printf 'authenticated as %s (token in SYSTEM KEYRING, not hosts.yml)\n' \
        "$(gh api user --jq .login 2>/dev/null || echo '?')"
    else printf 'PROBE FAILED\n'; fi
    printf 'forgejo: '
    if fj -H git.apps.kotona.app whoami >/dev/null 2>&1; then
      printf 'fj OAuth login present for git.apps.kotona.app\n'
    else printf 'PROBE FAILED\n'; fi
    ;;
  inventory)
    cat <<'INV'
github        gh (token in system KEYRING, NOT ~/.config/gh/hosts.yml) + ~/.ssh/github-agent-auth
forgejo       fj OAuth (~/.local/share/forgejo-cli/keys.json)
              ~/.config/forgejo/workstation-scope-token   [routine use]
              ~/.config/forgejo/admin-token               [break-glass]
git push      ALREADY WIRED -- ~/.gitconfig credential helpers cover both forges.
              No token handling needed. Just run git push.
vuoro-shared  ~/.config/vuoro/credentials/vuoro-shared-workstation  (via SPRINTCTL_VUORO_PROFILE)
vuoro-cloud   ~/.config/vuoro/credentials/vuoro-cloud.token
              AUDIENCE: vuoro-cloud APPLICATION operator API. vuo_operator_ prefix.
              NOT A FORGEJO CREDENTIAL -- Forgejo rejects it as malformed.
clusters      /projects/dev/appservice/clusters/.kube/config   (bare kubectl hits local kind!)
repo secrets  ~/.config/sops/age/keys.txt  (4 identities; decrypts appservice, vuoro-cloud, gitops-nixos)
hetzner       ~/.config/hcloud/cli.toml
INV
    ;;
esac
exit 0
