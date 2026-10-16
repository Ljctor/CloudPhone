# 03 — WireGuard phone tunnel

Create `10.20.0.0/24`, with the server at `10.20.0.1` and one phone peer at
`10.20.0.2`. UDP 51820 is the only additional public port. The phone private
key and import profile must never enter Git or command output.

## Check

```sh
: "${TARGET:?Set TARGET to setup-agent@SERVER_ADDRESS}"
ssh "$TARGET" 'sudo -n -u master sudo -n sh -eu' <<'REMOTE'
test "$(dpkg-query -W -f='${Status}\n' wireguard-tools | grep -c '^install ok installed$')" -eq 1
test "$(stat -c %a /etc/wireguard/wg0.conf)" = 600
test "$(stat -c %U:%G /etc/wireguard/wg0.conf)" = root:root
systemctl is-enabled --quiet wg-quick@wg0
systemctl is-active --quiet wg-quick@wg0
ip -4 address show dev wg0 | grep -q '10\.20\.0\.1/24'
wg show wg0 listen-port | grep -qx 51820
wg show wg0 allowed-ips | grep -q '10\.20\.0\.2/32'
nft list chain inet server_filter input | grep -Eq 'udp dport 51820 .* accept'
ss -lun | awk '$4 ~ /:51820$/ { found = 1 } END { exit !found }'
REMOTE
```

## Apply

Generate the server private key directly in `/etc/wireguard/server.key` with
mode 600. Create the phone tunnel in the WireGuard mobile application so the
phone private key never reaches the server, shell, Git, or chat. Transfer only
the phone public key into the server configuration. The phone needs only the
server public key, the server endpoint, address `10.20.0.2/32`, and
`AllowedIPs = 10.20.0.0/24`.

Write `/etc/wireguard/wg0.conf` with mode 600 and this structure:

```ini
[Interface]
Address = 10.20.0.1/24
ListenPort = 51820
PrivateKey = SERVER_PRIVATE_KEY

[Peer]
PublicKey = PHONE_PUBLIC_KEY
AllowedIPs = 10.20.0.2/32
```

Add this rule to `/etc/nftables.conf` immediately after the SSH rule:

```nft
udp dport 51820 ct state new accept
```

Install and activate WireGuard:

```sh
: "${TARGET:?Set TARGET to setup-agent@SERVER_ADDRESS}"
ssh "$TARGET" 'sudo -n -u master sudo -n sh -eu' <<'REMOTE'
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y wireguard-tools
install -m 644 /dev/stdin /etc/modules-load.d/wireguard.conf <<'CONFIG'
wireguard
CONFIG
modprobe wireguard
nft -c -f /etc/nftables.conf
nft -f /etc/nftables.conf
systemctl enable --now wg-quick@wg0
REMOTE
```

The client uses split tunneling with `AllowedIPs = 10.20.0.0/24` and
`PersistentKeepalive = 25`.
