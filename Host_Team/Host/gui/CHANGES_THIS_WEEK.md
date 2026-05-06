# Host GUI – Changes This Week

PowerPoint-ready summary. Each `##` heading is one slide; bullets are slide bullets; the *Why it matters* and *Files touched* lines are speaker notes / footers.

---

## Slide 1 — Overview

- Three themes shipped this week:
  1. **Multi-device query targeting** — pick one, several, or all edge devices for each query.
  2. **Query Window quality-of-life pass** — eight focused UX upgrades.
  3. **Production / Demo split** — `s1_start_app.py` is now demo-free; offline demo lives in its own runnable (`demo_start_app.py`) behind a typed backend contract.
- Backwards compatible: edges that ignore the new `target_devices` field still work (broadcast behavior preserved).
- Zero new dependencies. Pure PyQt6 + stdlib.

*Footer: 5 files changed + 1 new entry point · 0 new third-party packages*

---

## Slide 2 — Multi-device targeting (what the user sees)

- **Checkboxes** on every device card in *Available Devices*.
- **Selection summary** in the title bar: "Target: 3 devices selected" / "Target: All devices (broadcast)".
- **One-click "Clear"** button to reset selection to broadcast.
- **Chips strip** inside the Query window mirrors the selection.
- **`+ Add` dropdown** in the Query window to add any known device without going back.
- **`×`** on each chip removes that target; the device window's checkbox updates in real time.

*Why it matters: lets operators ask "what does Camera-3 see?" without flooding every edge device on the network.*

---

## Slide 3 — Multi-device targeting (under the hood)

- New optional field `target_devices: [str]` in the `query_request` packet body.
- `MQTTHostClient.send_query_request(query_text, target_devices=...)` — deduped, trimmed, omitted entirely when empty (broadcast).
- `HostCommandSender.send_query_request(...)` exposes the same arg to the GUI layer.
- `GUIHandler._handle_ui_query_sent(query_text, target_devices)` — forwards both; falls back to legacy single-arg callbacks via `try/except TypeError` so old test harnesses keep working.
- Two-way sync: `AvailableDevicesWindow ↔ QueryWindow` share state via `set_target_devices` / `set_targets_changed_callback`.

*Files touched: `host_client.py`, `gui_handler.py`, `s3_availableDevices.py`, `s4_query.py`, `s1_start_app.py`*

---

## Slide 4 — Example outgoing packet

Before:

```json
{ "header": { "message_type": "query_request", ... },
  "body":   { "query_id": "...", "query": "how many people?" } }
```

After (targeted):

```json
{ "header": { "message_type": "query_request", ... },
  "body":   { "query_id": "...",
              "query": "how many people?",
              "target_devices": ["Edge-A", "Edge-B"] } }
```

After (broadcast — unchanged): identical to "before".

*Edge-side contract: filter on `target_devices` if present and non-empty; otherwise treat as broadcast.*

---

## Slide 5 — QoL #10 · Press **Enter** to send

- `QLineEdit.returnPressed` wired to the send handler.
- One-line change, biggest single UX win.
- Reduces double-clicks and misfires on the small "Send" button.

*File: `s4_query.py`*

---

## Slide 6 — QoL #11 · Query history (↑ / ↓)

- New `_HistoryLineEdit` subclass intercepts arrow keys.
- Up = older entry, Down = newer; first Up snapshots the current draft so you can return to it.
- In-memory ring buffer of up to 50 entries; deduped against the most recent send.
- Placeholder text now reads "Enter query…   (Enter to send · ↑/↓ history)" so the feature is discoverable.

*File: `s4_query.py`*

---

## Slide 7 — QoL #12 · Clear returned images

- New "⌫ Clear" button in the *Images Returned* card header.
- Deletes thumbnails, clears the main preview, resets metadata cache.
- Auto-disables when there's nothing to clear.

*Why it matters: after a long demo, the right-hand grid can hold dozens of thumbnails. A single click resets it.*

---

## Slide 8 — QoL #13 · Copy response · Save image

- **⧉ Copy** — copies the current response text to the system clipboard. Brief "✓ Copied" confirmation flashes on the button.
- **⤓ Save** — opens a file dialog (PNG / JPEG) and writes the currently displayed image. Default filename embeds the response timestamp.
- Both buttons are disabled until something useful is on screen.

*Why it matters: makes evidence collection one click, not a screenshot tool.*

---

## Slide 9 — QoL #14 · Click image to enlarge

- Main preview is now cursor-pointer + tooltip "Click to view full size".
- If responses exist → opens the navigable Pop-Out.
- If only a one-off image is loaded → opens a lightweight `_ImageViewerDialog` (Esc to close).

*Why it matters: instant zoom, especially when verifying small detections.*

---

## Slide 10 — QoL #15 · Animated pending spinner

- Replaced static "Pending response..." text with a Braille spinner (⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏) ticking at 120 ms.
- Pending message also shows the target: *"Pending response from Edge-A…"* or *"Pending response from 3 devices…"*.
- Sells "the system is working" — kills the "did I click it?" double-send class of bug.

*File: `s4_query.py` + `s1_start_app.py` (target-aware message)*

---

## Slide 11 — QoL #16 · Query timeout warning

- 20-second `QTimer.singleShot` armed when a query goes pending.
- If no response arrives in time: pending row turns amber and displays *"⚠ No response after 20s — try again?"*; Send button re-enables so the user can retry.
- Auto-cancelled when a real response lands.

*Why it matters: previously a dropped MQTT response left the UI "pending" forever.*

---

## Slide 12 — QoL #17 · Show `query_id` badge

- Small monospace badge below the input: `qid: 7f3a2c91`.
- Matches the prefix logged by the broker / edge code, so cross-referencing logs is now eyeball-easy.

*Why it matters: zero-effort debugging when an edge replies to the wrong query.*

---

## Slide 13 — Production / Demo split

- `s1_start_app.py` is now **completely demo-free**. Every `[DEMO]` block was removed.
- New typed contract: `class HostBackend(Protocol)` with four methods —
  `set_on_packet`, `send_discovery_request`, `send_query_request`, `close`.
- `class MqttBackend` (production) wraps `HostCommandSender`.
- New `class DemoBackend` (demo) lives in `demo_query.py`, fakes every packet.
- New `def run_app(backend: HostBackend)` owns 100% of the GUI wiring; both
  entry points call it.

```
s1_start_app.py main()  →  run_app(MqttBackend(...))     # production
demo_start_app.py main() →  run_app(DemoBackend(...))    # offline demo
```

*Why it matters: production code has zero risk of accidentally executing demo paths. To delete demo mode entirely, remove two files (`demo_start_app.py`, `demo_query.py`) — nothing else references them.*

---

## Slide 14 — Demo flow (offline, no broker)

1. `python demo_start_app.py`
2. Click **Discover** → 4 fake edge devices appear (lobby / hallway / server room / parking).
3. Tick checkboxes on one or more → chips appear in the Query window.
4. Type any prompt, press **Enter** → one staggered fake response per target arrives, each tagged with that device's name in the *Edge Device* metadata field.

*The fake packets have the exact wire shape of real MQTT packets, so every `_on_packet` code path in `run_app` is exercised identically. The demo is a true integration test, not a UI mock.*

---

## Slide 15 — Security note on the "injector"

- The pattern is **constructor injection** at the entry-point level, not a DI container.
- No dynamic class loading, no plugin discovery, no deserialization, no reflective lookups keyed on user input. It's a function parameter.
- Attack surface is unchanged from before: an attacker with write access to the install dir could already edit `s1_start_app.py` directly.
- Tracked separately and unaffected: plaintext MQTT, broker creds via env vars, auth_api token handling.

---

## Slide 16 — Files changed (reference)

| File | Purpose of edit |
|---|---|
| `host_client.py` | `target_devices` parameter on `MQTTHostClient.send_query_request` and `HostCommandSender.send_query_request`; deduped + omitted when empty. |
| `gui_handler.py` | Query callback signature widened; forwards `target_devices`; legacy single-arg callbacks still work. |
| `s3_availableDevices.py` | Per-device checkboxes, selection summary label, "Clear" button, public `selected_devices` / `set_selected_devices` API; chips stay in sync via callback. |
| `s4_query.py` | New `_TargetChip`, `_HistoryLineEdit`, `_ImageViewerDialog` widgets. Targets row, +Add menu, chips strip. All eight QoL features live here. |
| `s1_start_app.py` | **Refactored.** Demo-free production entry point. Introduces `HostBackend` protocol, `MqttBackend`, and `run_app(backend)`. |
| `demo_query.py` | **Reworked.** Now exports `DemoBackend` (fakes discovery + query packets) instead of the old "intercept the query text" responder. |
| `demo_start_app.py` | **New.** Ten-line entry point — `run_app(DemoBackend())`. |

---

## Slide 17 — Verification

- Smoke tests (offscreen Qt) confirm:
  - Checkbox → chips → callback → packet body all wired correctly.
  - Removing a chip syncs back to the device-window checkboxes.
  - Outgoing packet contains `target_devices` only when non-empty.
  - `isinstance(DemoBackend(), HostBackend) == True` — Protocol contract satisfied.
  - `DemoBackend.send_discovery_request()` produces a `discovery_response` packet with the 4 fake devices.
  - `DemoBackend.send_query_request("...", ["A","B"])` produces 2 staggered `query_response` packets, both with the same `query_id`.
- No linter errors introduced.
- Existing test harness (`tests/full_gui_simulator.py`) untouched and still uses the legacy single-arg query callback — works via the `TypeError` fallback in `gui_handler`.

---

## Slide 18 — Saved for next week

(From the original QoL list — not implemented yet, picked off the top of the backlog.)

- MQTT connection indicator + manual Reconnect button
- Persist window geometry / broker IP via `QSettings`
- Settings dialog (broker / port / topics)
- Toast / snackbar notifier for non-fatal errors
- Per-device "Query this device" shortcut button on each card
- Search / filter box for devices
- Auto-refresh / heartbeat toggle on Discover
- Built-in raw-packet log panel (debug)
- Keyboard shortcuts: Ctrl+D Discover, Ctrl+Q Query window, Ctrl+L Clear, Ctrl+, Settings
- Confirm-before-exit when a query is in flight
