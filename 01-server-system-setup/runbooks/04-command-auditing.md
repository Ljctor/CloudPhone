# 04 — Command auditing

Install Linux Audit and record every external program executed from an
authenticated human or agent session. Audit events preserve the original SSH
login identity as `auid`/`loginuid`, while `uid` and `euid` identify the
functional account (`system-setup`, `master`, or root) executing the program.

This deliberately does not enable terminal-keystroke auditing: keystrokes can
capture passwords and other secrets. Shell built-ins such as `cd` do not create
an `execve` event, but executed programs and sudo activity are recorded.
Because `execve` records program arguments, secrets must never be passed on a
command line; use protected interactive prompts or standard input instead.

## Check

```sh
: "${TARGET:?Set TARGET to setup-agent@SERVER_ADDRESS}"
ssh "$TARGET" 'sudo -n -u system-setup sudo -n sh -eu' <<'REMOTE'
test "$(dpkg-query -W -f='${Status}\n' auditd | grep -c '^install ok installed$')" -eq 1
systemctl is-enabled --quiet auditd
systemctl is-active --quiet auditd
auditctl -s | grep -qx 'enabled 1'
auditctl -l | grep -q 'auid>=1000'
auditctl -l | grep -q 'auid!=-1\|auid!=unset\|auid!=4294967295'
auditctl -l | grep -q 'execve'
auditctl -l | grep -q 'user-commands'
grep -Eq '^[[:space:]]*session[[:space:]]+required[[:space:]]+pam_loginuid\.so' /etc/pam.d/sshd
REMOTE
```

## Apply

```sh
: "${TARGET:?Set TARGET to setup-agent@SERVER_ADDRESS}"
ssh "$TARGET" 'sudo -n -u system-setup sudo -n sh -eu' <<'REMOTE'
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y auditd

install -m 640 /dev/stdin /etc/audit/rules.d/40-user-commands.rules <<'RULES'
-a always,exit -F arch=b64 -S execve,execveat -F auid>=1000 -F auid!=unset -k user-commands
-a always,exit -F arch=b32 -S execve,execveat -F auid>=1000 -F auid!=unset -k user-commands
-w /etc/sudoers -p wa -k privilege-config
-w /etc/sudoers.d -p wa -k privilege-config
RULES

augenrules --load
systemctl enable auditd
service auditd restart
REMOTE
```

Useful read-only investigations:

```sh
sudo ausearch -k user-commands -i
sudo ausearch --loginuid setup-agent -i
sudo aureport --auth --summary -i
```

`auid` answers “who originally connected?”; `euid` answers “as which account
did the command run?”.
