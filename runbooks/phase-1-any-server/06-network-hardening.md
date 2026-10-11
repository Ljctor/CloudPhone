# 06 — Public network hardening

Move OpenSSH from port 22 to the private-use port 52242, allow only that port
through the host input firewall during phases 1–2, disable LLMNR, and enable an
OpenSSH Fail2ban jail. Phase 3 adds WireGuard UDP 51820 to the firewall.

## Check

```sh
: "${TARGET:?Set TARGET to setup-agent@SERVER_ADDRESS}"
ssh "$TARGET" 'sudo -n -u system-setup sudo -n sh -eu' <<'REMOTE'
test "$(dpkg-query -W -f='${Status}\n' nftables fail2ban | grep -c '^install ok installed$')" -eq 2
sshd -T | grep -qx 'port 52242'
ss -lnt | awk '$4 ~ /:52242$/ { found = 1 } END { exit !found }'
if ss -lnt | awk '$4 ~ /:22$/ { found = 1 } END { exit !found }'; then exit 1; fi
systemctl is-enabled --quiet nftables
systemctl is-active --quiet nftables
nft list chain inet server_filter input | grep -q 'policy drop'
nft list chain inet server_filter input | grep -Eq 'tcp dport 52242 .* accept'
systemctl is-enabled --quiet fail2ban
systemctl is-active --quiet fail2ban
fail2ban-client status sshd | grep -q 'Jail list\|Status for the jail: sshd'
resolvectl status | grep -Eq 'Protocols:.*-LLMNR'
REMOTE
```

## Apply

Install the packages and move SSH first. Keep the current session open:

```sh
: "${TARGET:?Set TARGET to setup-agent@SERVER_ADDRESS}"
ssh "$TARGET" 'sudo -n -u system-setup sudo -n sh -eu' <<'REMOTE'
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y nftables fail2ban
install -m 644 /dev/stdin /etc/ssh/sshd_config.d/20-custom-port.conf <<'CONFIG'
Port 52242
CONFIG
sshd -t
systemctl restart ssh
REMOTE
```

Prove a fresh connection on the new port before enabling the firewall:

```sh
ssh -p 52242 -o BatchMode=yes -o ConnectTimeout=10 "$TARGET" 'true'
```

Then install the firewall and Fail2ban configuration through port 52242:

```sh
ssh -p 52242 "$TARGET" 'sudo -n -u system-setup sudo -n sh -eu' <<'REMOTE'
install -m 644 /dev/stdin /etc/modules-load.d/server-firewall.conf <<'CONFIG'
nf_conntrack
nft_ct
CONFIG
modprobe nf_conntrack
modprobe nft_ct
install -m 644 /dev/stdin /etc/nftables.conf <<'NFT'
#!/usr/sbin/nft -f
flush ruleset
table inet server_filter {
  chain input {
    type filter hook input priority filter; policy drop;
    iifname "lo" accept
    ct state established,related accept
    ct state invalid drop
    ip protocol icmp accept
    ip6 nexthdr ipv6-icmp accept
    tcp dport 52242 ct state new accept
  }
}
NFT
install -d -m 755 /etc/systemd/resolved.conf.d
install -m 644 /dev/stdin /etc/systemd/resolved.conf.d/20-disable-llmnr.conf <<'CONFIG'
[Resolve]
LLMNR=no
CONFIG
install -m 644 /dev/stdin /etc/fail2ban/jail.d/sshd.local <<'CONFIG'
[sshd]
enabled = true
port = 52242
backend = systemd
maxretry = 3
findtime = 5m
bantime = 30m
CONFIG
nft -f /etc/nftables.conf
systemctl enable --now nftables
systemctl restart systemd-resolved
systemctl enable --now fail2ban
systemctl restart fail2ban
systemctl restart docker 2>/dev/null || true
REMOTE
```

Update the operator's SSH client to use port 52242, prove a fresh connection,
then rerun Check.
