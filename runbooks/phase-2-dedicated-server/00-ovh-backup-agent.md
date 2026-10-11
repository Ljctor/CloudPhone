# 00 — OVH Backup Agent

This phase applies only to OVH Bare Metal dedicated servers. Install the OVH
Backup Agent (Veeam) only after the Backup Agent service has been activated in
the OVHcloud Control Panel and this server appears in its `Agents` list.

The generated installer URLs are signed credentials. Never put them in this
repository, shell history, chat, or a persistent configuration file.

## Check

```sh
: "${TARGET:?Set TARGET to setup-agent@SERVER_ADDRESS}"
ssh "$TARGET" 'sudo -n -u system-setup sudo -n sh -eu' <<'REMOTE'
dpkg-query -W -f='${Status}\n' veeamma veeam veeam-libs |
  grep -c '^install ok installed$' | grep -qx 3
status=$(veeamconsoleconfig -s)
printf '%s\n' "$status" | grep -Eq 'Connection state[[:space:]]*:[[:space:]]*Connected'
printf '%s\n' "$status" | grep -Eq 'Status[[:space:]]*:[[:space:]]*Running'
REMOTE
```

## Apply

In the OVHcloud Control Panel, activate `Bare Metal Cloud > Backup Agent`, add
this server in `Agents`, and select Linux to obtain the temporary signed URL.
Do not paste that URL into a command line: command auditing records process
arguments. Enter it through a silent prompt and pass it to `curl` on standard
input instead.

Connect as `setup-agent`, then enter the functional account before running the
installer:

```sh
sudo -n -u system-setup -i
read -r -s -p 'OVH installer URL: ' installer_url
printf '\n'
printf 'url = "%s"\n' "$installer_url" |
  curl --fail --location --config - --output /tmp/ovh-backup-agent-installer.sh
unset installer_url
chmod 700 /tmp/ovh-backup-agent-installer.sh
sudo /tmp/ovh-backup-agent-installer.sh
shred --remove /tmp/ovh-backup-agent-installer.sh
```

The installer deploys the Veeam Management Agent; OVH then deploys the Backup
Agent and its policy. Wait until `veeamconsoleconfig -s` reports both
`Connected` and `Running`, then rerun **Check**.

The server needs outbound HTTPS for the download and outbound TCP/UDP 6180 to
the VSPC gateway. No inbound Backup Agent port is required.
