# LAS-VICA Expected Model Behavior and Test Procedure

This document defines expected behavior and a thorough test process for team members.

Use this to:
- verify the system behaves correctly end-to-end
- run repeatable functional and integration tests
- identify regressions early
- report issues with consistent evidence

## 1. Expected Runtime Behavior

## 1.1 Discovery Behavior

Expected:
1. Clicking `Discover` sends a discovery request from Host.
2. Network relay returns a discovery response using cached edge status.
3. GUI device list populates with online/offline and health metadata.

Pass criteria:
- discovered devices appear within 5 seconds in typical lab conditions
- each device has a readable name and status

## 1.2 Targeted Query Behavior

Expected:
1. If target devices are selected in GUI, query request includes `target_devices`.
2. Relay routes query only to selected edge topics.
3. Only selected edge devices return `query_response` packets.

Pass criteria:
- only selected edges respond
- non-selected edges do not respond to that query ID

## 1.3 Broadcast Query Behavior

Expected:
1. If no target devices are selected, query is broadcast.
2. All online edges may respond.

Pass criteria:
- multiple online edges respond
- each response contains source device and query ID

## 1.4 Query Response Rendering Behavior

Expected:
- GUI shows pending state after send.
- GUI clears pending when active query responses arrive.
- GUI renders returned image and metadata.
- GUI tracks query IDs for debugging.

Pass criteria:
- no GUI freeze/crash
- response text and image are visible
- metadata updates with source device and timestamp

## 1.5 Edge Status Behavior

Expected:
- edge publishes periodic status packets
- GUI reflects updated status/health data

Pass criteria:
- status metadata updates at least every few seconds
- offline edges eventually reflect offline/absent behavior

What to should actively look for:
1. Status freshness in GUI:
- CPU, RAM, and connection fields should change over time, not stay frozen.
- A healthy edge should appear to refresh every few seconds.

2. Correct device identity:
- Status updates should stay tied to the correct edge name.
- Data from one edge should not appear under another edge card.

3. Reasonable metric ranges:
- CPU/RAM/GPU percentages should be between 0 and 100.
- Network strength should be a realistic negative dBm value (for example around -50 to -90).

4. Processing flag behavior:
- When a query is running, an edge may show a processing/active state.
- After response completes, state should return to idle/normal.

5. Offline transition behavior:
- If an edge is powered off or disconnected, it should stop updating.
- GUI should eventually show it as offline or remove it after re-discovery.

Common warning signs (possible bug):
- stale values for 30+ seconds while edge is online
- duplicate edge entries with same name
- impossible values (for example 340% CPU, positive network dBm)
- edge never returns to idle after query completion

## 2. Test Levels

Run tests in this order.

1. Offline GUI sanity (no broker)
2. Real relay with mock edges
3. Full lab integration with real edge model
4. Negative/failure tests

What no broker means:
- No MQTT broker process is running.
- No network publish/subscribe path is used.
- No real relay and no real edge device is required.
- Responses are simulated in-process by a demo backend.

In this repo, no broker mode is this command:

```bash
python Network/test_suite/run_gui_targeting_offline.py
```

What this level validates:
- GUI flow works (Discover, select target devices, send query, render responses).
- Targeted vs broadcast behavior in the UI logic.
- Basic packet handling shape expected by the GUI.

What this level does not validate:
- MQTT connectivity
- relay routing correctness over topics
- real edge model/camera inference behavior

How to should interpret each level:

1. Offline GUI sanity (no broker):
- Goal: prove UI behavior is correct in isolation.
- Look for: no crashes, proper target selection, expected response count.

2. Real relay with mock edges:
- Goal: prove routing through broker + relay is correct.
- Look for: only selected edges respond in targeted mode, all respond in broadcast mode.

3. Full lab integration with real edge model:
- Goal: prove end-to-end behavior with live model and camera.
- Look for: realistic inference latency, valid responses, stable status updates under load.

4. Negative/failure tests:
- Goal: prove system fails gracefully and recovers.
- Look for: clear errors, no hard crashes, recovery after restoring dependencies.

## 3. Test Environment Matrix

Use this matrix as a minimum coverage checklist. Detailed commands and procedures are in Sections 2 and 4.

Minimum required setup:
- Host machine: Windows laptop running the GUI.
- Relay machine: one dedicated lab computer (recommended NUC) running `Network/server.py`.
- Edge coverage: run once with 1 active edge, then run again with 3+ active edges.

Minimum required mode coverage:
- Offline backend mode (no broker): see Section 4.1.
- Mock edge fleet mode (real broker + relay): see Section 4.2.
- Real edge model mode: see Section 4.4.

Pass condition for matrix coverage:
- All three modes complete successfully.
- Both 1-edge and 3+-edge runs pass.
- No crashes, no stuck pending state, and responses match selected targets.

## 4. Test Cases

## 4.1 Offline GUI Sanity

Purpose:
- verify GUI workflow independent of network

Command:

```bash
python Network/test_suite/run_gui_targeting_offline.py
```

Steps:
1. Click Discover.
2. Select one device.
3. Send query.
4. Clear selection.
5. Send second query.

Expected:
- first query returns one device response
- second query returns broadcast responses

## 4.2 Relay + Mock Edge Integration

Purpose:
- verify routing logic and packet flow through MQTT relay

Command:

```bash
python Network/test_suite/run_all_gui_routing_test.py --broker <BROKER_IP> --port 1883 --edge-count 3
```

Steps:
1. In GUI click Discover.
2. Select one edge.
3. Send query and record responding edge names.
4. Clear selection.
5. Send query again.

Expected:
- targeted run: only chosen edge responds
- broadcast run: all mock edges respond

## 4.3 Unit-Style Routing Regression

Purpose:
- catch routing regressions quickly in CI/local runs

Commands:

```bash
pytest -q Network/test_suite/test_server_routing.py
pytest -q Network/test_suite/test_offline_targeting_backend.py
```

Expected:
- all tests pass

## 4.4 Full Real-Lab Integration

Purpose:
- validate with real edge model and camera input

Startup order:
1. broker
2. `python Network/server.py`
3. `python Edge/client.py` on each edge
4. `python Host_Team/Host/gui/s1_start_app.py`

Test prompts (example set):
- "Describe what you see"
- "How many people are visible?"
- "Is there a vehicle in frame?"

Expected:
- edge receives query and returns model response packets
- GUI displays responses without crashes
- response source matches selected target(s)

## 5. Negative and Failure Tests

Run each of these and verify graceful behavior.

## 5.1 Broker Down Before Startup

Action:
- stop broker, then start host/relay/edge scripts

Expected:
- clear connection errors in logs
- no hard crash loops
- after broker starts, reconnect behavior is recoverable

## 5.2 Edge Drops Mid-Session

Action:
- disconnect one edge after discover

Expected:
- remaining edges still respond
- disconnected edge stops responding
- GUI remains usable

## 5.3 Invalid/Empty Query

Action:
- send empty query or whitespace

Expected:
- query should not be sent (or should fail cleanly)
- no crash

## 5.4 Targeting Non-Existent Device

Action:
- simulate stale selected device not currently online

Expected:
- no response from missing device
- no crash
- operator can recover by re-running Discover

## 6. Performance and Stability Checks

Record these for at least one run:

1. Discover latency
2. Query round-trip latency per edge
3. GUI responsiveness under repeated queries
4. Edge CPU/RAM trends during sustained use

Suggested thresholds (initial lab targets):
- Discover: less than 5 s
- First query response: less than 20 s
- No GUI hangs during 10 consecutive queries

## 7. Evidence Collection for Every Test Run

Capture and attach:

1. Host GUI screenshot after responses
2. Host console logs
3. Relay logs
4. Edge logs
5. exact query text used
6. selected target device list
7. query ID(s)

## 8. Bug Report Template

Use this exact format:

```text
Title:
Environment:
- Host OS:
- Broker IP/Port:
- Edge device(s):
- Commit/branch:

Steps to Reproduce:
1.
2.
3.

Expected:
Actual:

Evidence:
- query_id:
- screenshots:
- host logs:
- relay logs:
- edge logs:

Severity:
```

## 9. Exit Criteria (Team Member Sign-Off)

A test cycle is complete when all are true:

1. Offline GUI sanity passes.
2. Mock relay routing passes for targeted and broadcast.
3. Full lab integration passes with real edge model.
4. Negative tests do not crash system.
5. Evidence is archived and bug reports filed for any failures.

If these criteria are met, software is ready for the next integration iteration.
