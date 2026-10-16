# Legacy reference server layout

How the first server was set up before the four-part layout: account
`master`, SDK in `/opt/android-sdk`, AVD `slayer-google-test` in
`/opt/android-avd`, services `android-emulator*`, page on port 8000.

That server still runs this layout. Keep these files to inspect or verify it
(`verify.sh setup-agent@SERVER_ADDRESS`); do not use them for a new install,
which follows parts 01–04. A later migration moves its AVD into
`/var/lib/cloudphone/avd` without losing data.
