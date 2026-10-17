# 02 — WireGuard server

Cloud Phone's web page and gateway have no login, so they must never be
reachable from the internet. This guide puts them behind
[WireGuard](https://www.wireguard.com/), a small VPN: only devices whose key
you added can open the phone, all traffic is encrypted, and the only port
opened to the internet is **UDP 51820**.

Network used in this guide (change it if `10.20.0.0/24` is already in use on
your networks):

| Host | WireGuard address |
|---|---|
| Server | `10.20.0.1` |
| Your phone | `10.20.0.2` |
| Another device (optional) | `10.20.0.3`, `10.20.0.4`… |

## Scripted path

From an unpacked release (or this repository) on the server, as root:

```sh
02-wireguard-server/scripts/install.sh                      # wg0, key, firewall, service
02-wireguard-server/scripts/add-peer.sh phone 'PUBLIC_KEY' 10.20.0.2
02-wireguard-server/scripts/verify.sh                       # read-only, prints PASS
02-wireguard-server/scripts/revoke-peer.sh 'PUBLIC_KEY'     # remove a device
02-wireguard-server/scripts/nft-allow.sh NAME 'RULE'        # open a port, persistently
```

`add-peer.sh` prints the values to enter on the device. An agent follows
`runbooks/` (see `AGENTS.md`). The rest of this page is the same setup done by
hand, with the firewall alternatives (ufw, provider firewall) and
troubleshooting.

## Manual path

Run the server commands in a root shell (`sudo -i`).

### 1. Install WireGuard on the server

```sh
apt-get update
apt-get install -y wireguard-tools
```

Create the server's key pair. The private key is written straight to a file
readable only by root; it is never printed:

```sh
umask 077
wg genkey > /etc/wireguard/server.key
wg pubkey < /etc/wireguard/server.key > /etc/wireguard/server.pub
cat /etc/wireguard/server.pub      # public: you will give it to the phone
```

### 2. Create the tunnel on the phone

Install the official **WireGuard** app (Google Play or App Store), then:

1. tap **+** → **Create from scratch**;
2. name the tunnel `cloudphone`;
3. tap the **generate** icon next to *Private key*. The app creates the phone's
   key pair; the private key never leaves the phone;
4. **Addresses**: `10.20.0.2/32`;
5. copy the **Public key** shown by the app and send it to yourself
   (it is public: an e-mail or a note is fine).

Keep the screen open; you finish it in step 5.

### 3. Configure the server's tunnel

Replace `PHONE_PUBLIC_KEY` with the phone's public key, then run:

```sh
umask 077
cat > /etc/wireguard/wg0.conf <<EOF
[Interface]
Address = 10.20.0.1/24
ListenPort = 51820
PrivateKey = $(cat /etc/wireguard/server.key)

[Peer]
# phone
PublicKey = PHONE_PUBLIC_KEY
AllowedIPs = 10.20.0.2/32
EOF
chmod 600 /etc/wireguard/wg0.conf
```

Start it now and at every boot:

```sh
systemctl enable --now wg-quick@wg0
wg show wg0
```

### 4. Firewall

The firewall must:

- accept **UDP 51820** from the internet (WireGuard);
- accept **TCP 8000** (`WEB_PORT`, the page and its API on one port) and **UDP
  32768-60999** (the WebRTC video) only on the `wg0` interface;
- keep your SSH port open, or you will lock yourself out.

> Keep a second SSH session open while you change the firewall, and check the
> rules before loading them. If your provider offers a rescue console, know
> how to reach it.

#### With nftables (Debian's default)

If the server has no firewall yet, this is a complete `/etc/nftables.conf`.
**Replace `22` with your SSH port** if you changed it:

```nft
#!/usr/sbin/nft -f
flush ruleset

table inet filter {
  chain input {
    type filter hook input priority 0; policy drop;
    ct state established,related accept
    ct state invalid drop
    iif "lo" accept
    meta l4proto { icmp, ipv6-icmp } accept
    tcp dport 22 accept
    udp dport 51820 accept
    iifname "wg0" tcp dport 8000 accept
    iifname "wg0" udp dport 32768-60999 accept
  }
  chain forward {
    type filter hook forward priority 0; policy drop;
  }
}
```

If you already have an nftables ruleset, add only the last three `accept`
rules to its input chain. Then check and apply:

```sh
nft -c -f /etc/nftables.conf     # syntax check, changes nothing
nft -f /etc/nftables.conf
systemctl enable nftables
```

#### With ufw (Ubuntu's default)

```sh
ufw allow 51820/udp
ufw allow in on wg0 to any port 8000 proto tcp
ufw allow in on wg0 to any port 32768:60999 proto udp
ufw status verbose
```

If ufw is not enabled yet, allow SSH first (`ufw allow OpenSSH`), then
`ufw enable`.

#### Hosting provider firewall

Some providers filter traffic before it reaches the server (for example an
optional network firewall on dedicated servers, or security groups on cloud
VMs). If one is active, allow **UDP 51820** there as well.

### 5. Finish the phone's tunnel

Back in the WireGuard app, tap **Add peer**:

| Field | Value |
|---|---|
| Public key | the content of `/etc/wireguard/server.pub` |
| Endpoint | `SERVER_PUBLIC_IP:51820` (or the server's DNS name) |
| Allowed IPs | `10.20.0.0/24` |
| Persistent keepalive | `25` |

`Allowed IPs = 10.20.0.0/24` sends only Cloud Phone's traffic through the
tunnel; the rest of the phone's traffic goes out normally. Save, then switch
the tunnel on.

On the server, `wg show wg0` now shows a *latest handshake* for the phone.

### 6. Make Cloud Phone listen only on the VPN

Bind the web page and the gateway to the WireGuard address, so they are not
listening on the public interface at all, even if the firewall changes:

```sh
# from the unpacked release
sudo ./install.sh --listen 10.20.0.1
```

or edit `LISTEN_ADDRESS=10.20.0.1` in `/etc/cloudphone/cloudphone.conf`, then
`systemctl restart cloudphone-gateway`. At boot, the services
retry until the tunnel is up.

On the phone, with the tunnel on, open **http://10.20.0.1:8000/**.

### Adding another device

Create its tunnel the same way with the next address (`10.20.0.3/32`), then
append a peer on the server and reload without dropping existing sessions:

```sh
cat >> /etc/wireguard/wg0.conf <<'EOF'

[Peer]
# laptop
PublicKey = DEVICE_PUBLIC_KEY
AllowedIPs = 10.20.0.3/32
EOF
wg syncconf wg0 <(wg-quick strip wg0)
```

On Linux, macOS or Windows, the client configuration file looks like this:

```ini
[Interface]
PrivateKey = <generated on that device>
Address = 10.20.0.3/32

[Peer]
PublicKey = <content of /etc/wireguard/server.pub>
Endpoint = SERVER_PUBLIC_IP:51820
AllowedIPs = 10.20.0.0/24
PersistentKeepalive = 25
```

To revoke a device, delete its `[Peer]` block and run the same
`wg syncconf` command.

## Troubleshooting

| Symptom | Check |
|---|---|
| No *latest handshake* in `wg show` | UDP 51820 blocked: server firewall, provider firewall, or a wrong endpoint or key on the phone. |
| Handshake OK but the page does not load | `LISTEN_ADDRESS` and the firewall rule for TCP 8000 on `wg0`; `curl http://10.20.0.1:8000/` on the server. |
| Page loads, then "The video does not connect" | UDP 32768-60999 must be accepted on `wg0` for the WebRTC video. |
| Page shows "Server unreachable" | The tunnel is off on this device, or the handshake stopped: check the app and `wg show`. |
| Works on Wi-Fi, not on mobile data | Some networks block UDP; keep `PersistentKeepalive = 25`, or try another network. |
