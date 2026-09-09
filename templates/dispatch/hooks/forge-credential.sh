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
    # PROBED, not asserted. This block used to be a static heredoc, and on
    # 2026-09-09 every forgejo line in it was false: it named three token files
    # that do not exist and a ~/.gitconfig that does not exist either (git
    # config is XDG, at ~/.config/git/config). A session read it, believed it,
    # and spent its opening moves reasoning from credentials it did not have.
    # An inventory that cannot observe what it lists is the same defect this
    # hook exists to prevent, so every line below is a live check.
    ex() { if [ -e "$1" ]; then printf 'EXISTS'; else printf 'MISSING'; fi; }
    have() { command -v "$1" >/dev/null 2>&1 && printf 'on PATH' || printf 'NOT on PATH'; }
    cb_dir="${HOME}/.config/cred-broker/workstation"

    printf 'github        gh: %s   ~/.ssh/github-agent-auth: %s\n' \
      "$(have gh)" "$(ex "${HOME}/.ssh/github-agent-auth")"
    printf 'forgejo API   fj OAuth keys.json: %s\n' \
      "$(ex "${HOME}/.local/share/forgejo-cli/keys.json")"
    printf '              workstation-scope-token: %s   admin-token: %s\n' \
      "$(ex "${HOME}/.config/forgejo/workstation-scope-token")" \
      "$(ex "${HOME}/.config/forgejo/admin-token")"
    printf 'git config    ~/.gitconfig: %s   ~/.config/git/config: %s  (XDG is the real one)\n' \
      "$(ex "${HOME}/.gitconfig")" "$(ex "${HOME}/.config/git/config")"
    printf 'git push      github https: gh helper. forgejo ssh: forgejo-ssh...:2222 (works).\n'
    printf '              forgejo https: git-credential-fj needs keys.json above -- if that\n'
    printf '              says MISSING, plain https push to the forge CANNOT work. Use ssh,\n'
    printf '              or the broker helper below. Do not conclude "no forge access".\n'
    printf 'cred-broker   credctl: %s\n' "$(have credctl)"
    printf '              client.crt: %s  session.json: %s  server-ca.crt: %s\n' \
      "$(ex "${cb_dir}/client.crt")" "$(ex "${cb_dir}/session.json")" \
      "$(ex "${cb_dir}/server-ca.crt")"
    if [ -r "${cb_dir}/client.crt" ] && command -v openssl >/dev/null 2>&1; then
      if openssl x509 -in "${cb_dir}/client.crt" -noout -checkend 0 >/dev/null 2>&1; then
        printf '              client certificate: VALID until %s\n' \
          "$(openssl x509 -in "${cb_dir}/client.crt" -noout -enddate 2>/dev/null | cut -d= -f2-)"
      else
        printf '              client certificate: EXPIRED -- run cred-broker-refresh-identity.sh\n'
      fi
    fi
    printf '              renewal timer: %s\n' \
      "$(systemctl --user is-enabled cred-broker-identity.timer 2>/dev/null || echo 'NOT INSTALLED')"
    printf '              HOW: credctl exec <capability> --repository forgejo:<owner>/<repo> -- <cmd>\n'
    printf '              (FJ_TOKEN is injected into the child). For git over https add BOTH\n'
    printf '              -c credential.useHttpPath=true and\n'
    printf '              -c "credential.helper=!credctl git-credential --capability repo.write"\n'
    printf '              -- without useHttpPath git sends no repo path and the helper returns\n'
    printf '              nothing, which surfaces as "could not read Username", not as an error.\n'
    printf '              Capabilities: repo.read repo.write pr.merge (forgejo), + pr.manage (github).\n'
    printf '              SETUP if missing / BROKEN: appservice/docs/runbooks/cred-broker-host-identity.md\n'
    printf '              PROVE a forge integration: appservice/docs/scripts/cred-broker-forgejo-canary.sh\n'
    printf 'vuoro-shared  %s  (via SPRINTCTL_VUORO_PROFILE)\n' \
      "$(ex "${HOME}/.config/vuoro/credentials/vuoro-shared-workstation")"
    printf 'vuoro-cloud   %s  -- APPLICATION operator API (vuo_operator_), NOT a forgejo credential\n' \
      "$(ex "${HOME}/.config/vuoro/credentials/vuoro-cloud.token")"
    printf 'clusters      /projects/dev/appservice/clusters/.kube/config: %s  (bare kubectl hits local kind!)\n' \
      "$(ex /projects/dev/appservice/clusters/.kube/config)"
    printf 'repo secrets  ~/.config/sops/age/keys.txt: %s\n' "$(ex "${HOME}/.config/sops/age/keys.txt")"
    printf 'hetzner       ~/.config/hcloud/cli.toml: %s\n' "$(ex "${HOME}/.config/hcloud/cli.toml")"
    ;;
esac
exit 0
