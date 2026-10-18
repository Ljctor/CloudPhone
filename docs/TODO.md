# Known bugs

Tests of the black-box suite (`tests/e2e`) that fail on the current code.
Owner: the agent maintaining the gateway and the page (each entry says
what is known; fix or explain before the hexagonal refactor reaches that
domain).

| Test | Diagnosis |
|---|---|
| `ui_changes::the_page_can_still_post_after_a_change_restarted_the_gateway` | The page keeps the per-start token from its first load; after a change restarts the gateway, every POST is refused with "Missing or invalid page token" until the page is reloaded. |
| `display::the_two_minute_limit_holds_after_a_successful_change` | Not diagnosed yet: the limit between two screen size changes is not enforced after a successful change in the fake emulator. |
| `plugins::a_plugin_reads_androids_screen` | Not diagnosed yet: a plugin's screenshot of Android does not come back as expected under the fake emulator. |
| `plugins::a_plugin_reads_a_1080p_screen` | Not diagnosed yet: same as above at 1080p; probably the same cause. |
