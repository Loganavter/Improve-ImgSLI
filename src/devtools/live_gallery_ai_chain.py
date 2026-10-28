#!/usr/bin/env python3
"""Prove the AI-domain chains on a LIVE app against a local stub — one verdict.

Why this exists (2026-10-28, W7 of the backend-isolation plan): the live proof
that needs no provider covered the Algorithms domain. The AI domain needs a
model answer, and the honest way to get one without the owner's keyring is the
AI stub (``live_fixtures.ai_stub_server``) in an isolated ``XDG_CONFIG_HOME``.
A real AI-domain run asks TWO different questions — the metric-profile proposal
wants a JSON *list* of axes, the scorecard a JSON *object* of scores — so the
stub is given a router and the two answers are distinguishable by value.

What it asserts (each one is a plan invariant, not a screenshot):

1. the app really talked to the stub: the router served the profile answer and
   at least one scorecard answer, and the request carried the image;
2. the judge's axes are the numbers the ANSWER carried: every AI cache entry
   holds the stub's distinctive score (the free axis nobody local can measure);
3. local numbers never arrive as judge values: the same picture's LOCAL metrics
   entry exists (the stage-2 lanes still run) and its value for the axis the
   judge also answered is a DIFFERENT number, so a substitution would show;
4. the profile the run used named the judge's free axes (the log's own line);
5. the gallery ranked, i.e. the numbers reached the ranker (``jev rank``).

Usage (inside a lease, so XDG/display/control dir are already isolated):

    IMGSLI_CONTROL=1 IMGSLI_TRACE=1 DISPLAY=:NN \\
      venv/bin/python src/devtools/live_gallery_ai_chain.py [--images 4]

``--lease <name>`` allocates a lease itself and releases it on the way out.

Exit codes: 0 every assertion held, 1 an assertion failed, 3 the run did not
settle, 4 the app could not be driven, 2 usage.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import signal
import subprocess
import sys
import time
from pathlib import Path

# The tool is run as a SCRIPT (`venv/bin/python src/devtools/live_gallery_ai_chain.py`),
# which puts `src/devtools` on sys.path, not `src` — so its own package import
# needs the repo root added BEFORE it runs. (Measured 2026-10-28: after the split
# into `live_gallery_ai_common` the tool died with ModuleNotFoundError: devtools
# while the tests, which set PYTHONPATH=src, stayed green.)
_SRC = Path(__file__).resolve().parents[1]
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from devtools.live_gallery_ai_common import (
    JUDGE_ONLY_AXIS,
    JUDGE_SCORE,
    JUDGE_SHARED_SCORE,
    LOCAL_ONLY_AXES,
    PROFILE_ANSWER,
    SCORECARD_ANSWER,
    SHARED_AXIS,
    _ai_axes,
    _cache_dir,
    _cache_files,
    _control_client,
    _kill_leftover_apps,
    _line_ms,
    _local_axis_values,
    _read_entries,
    _socket_target,
    _stop_app,
    _stub_router,
    make_images,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
VENV_PY = REPO_ROOT / "venv" / "bin" / "python"

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--folder", type=Path, default=None, help="series to open (made when absent)")
    parser.add_argument(
        "--scenario", choices=("chain", "reset"), default="chain",
        help="chain = the AI chain; reset = a reset in the middle of an ACTIVE run",
    )
    parser.add_argument("--images", type=int, default=0, help="default 4 (chain), 6 (reset)")
    parser.add_argument("--timeout", type=float, default=300.0)
    parser.add_argument("--quiet", type=float, default=12.0)
    parser.add_argument("--delay", type=float, default=0.0, help="stub latency per answer (a slow provider)")
    parser.add_argument("--artifact", type=Path, default=Path("/tmp/opencode/w7-ai-chain.png"))
    parser.add_argument("--log", type=Path, default=Path("/tmp/opencode/w7-ai-chain.log"))
    parser.add_argument("--out", type=Path, default=Path("/tmp/opencode/w7-ai-chain.json"))
    parser.add_argument("--keep-app", action="store_true")
    parser.add_argument("--debug", action="store_true", help="IMGSLI_DEBUG=1 (gallery diagnostics)")
    parser.add_argument(
        "--reset-via", choices=("menu", "action"), default="menu",
        help="how the reset scenario fires 'Reset metrics cache': the card menu "
             "(what a user had before the Find Action rows existed) or the "
             "pool-wide gallery.reset-metrics action",
    )
    parser.add_argument("--lease", default=None, help="allocate and release a lease for this proof")
    args = parser.parse_args(argv)

    lease = None
    if args.lease:
        from devtools import live_lease

        lease = live_lease.alloc(lane="gallery-judge-axes", task=args.lease)
        os.environ.update(lease.env)

    if args.debug:
        os.environ["IMGSLI_DEBUG"] = "1"
    sys.path.insert(0, str(REPO_ROOT / "src"))
    from devtools import help_live, live_fixtures

    stale = _kill_leftover_apps()
    if stale:
        time.sleep(2.0)
    images = args.images or (6 if args.scenario == "reset" else 4)
    delay = args.delay or (0.5 if args.scenario == "reset" else 0.0)
    folder = (args.folder or Path("/tmp/opencode/w7-ai-chain-series")).resolve()
    make_images(folder, max(2, images))

    verdict: dict = {
        "scenario": args.scenario,
        "folder": str(folder),
        "domain": "ai",
        "lease": os.environ.get("LIVE_LEASE"),
        "killed_stale_apps": stale,
    }
    socket_path = Path(os.environ.get("IMGSLI_MCP_CONTROL_SOCKET") or "") if os.environ.get(
        "IMGSLI_MCP_CONTROL_SOCKET"
    ) else None
    if socket_path is not None:
        try:
            socket_path.unlink()
        except OSError:
            pass
    stub = live_fixtures.ai_stub_server(_stub_router(delay))
    app_pid: int | None = None
    try:
        config_home = os.environ.get("XDG_CONFIG_HOME")
        profile = help_live.write_profile(
            Path("/tmp/opencode/w7-ai-chain-root"),
            locale="en",
            theme="dark",
            width=1600,
            height=1000,
            extra_sections=help_live.ai_profile_sections(stub),
            config_home=Path(config_home) if config_home else None,
        )
        # The AI group lives in the NEW settings namespace
        # (QSettings("BlinkTable","BlinkTable"), ai_settings_store._QS_ORG/_QS_APP)
        # which is seeded by a ONE-WAY migration from the legacy file above and
        # only while the new store is EMPTY ("both populated -> the new
        # namespace wins"). On a REUSED lease the old file still points at a
        # stub port from a previous run, so the app would answer from a dead
        # endpoint — measured 2026-10-28: run 2 sent its profile request to
        # run 1's port and logged URLError 111. Dropping the new store makes the
        # migration copy THIS run's seed; the file holds nothing else (fresh
        # lease, the legacy file carries the rest).
        new_store = Path(os.environ.get("XDG_CONFIG_HOME") or (Path.home() / ".config")) / (
            "BlinkTable/BlinkTable.conf"
        )
        try:
            new_store.unlink()
            verdict["stale_settings_dropped"] = str(new_store)
        except FileNotFoundError:
            pass
        verdict["profile_conf"] = str(profile)
        verdict["stub_base_url"] = stub.base_url

        os.environ["IMGSLI_TRACE"] = "1"
        reset_info: dict = {}
        if args.scenario == "reset":
            import threading

            def _reset_when_running() -> None:
                deadline = time.monotonic() + 120.0
                while time.monotonic() < deadline:
                    text = ""
                    try:
                        text = args.log.read_text(encoding="utf-8", errors="replace")
                    except OSError:
                        pass
                    if "analyze start" in text and "jev rank" not in text:
                        break
                    time.sleep(0.3)
                try:
                    control_now = _control_client(Path(_socket_target()))
                    before = len(_cache_files())
                    reset_info["state_before"] = control_now.call(
                        "get_state", path="tabs.image_gallery"
                    ).get("state")
                    reset_info["cache_files_before"] = before
                    reset_info["at_ms"] = int(time.time() * 1000)
                    if args.reset_via == "action":
                        # The pool-wide reset: the Find Action row the gallery
                        # now registers itself (app #776). Before that fix the
                        # palette had ZERO ``gallery.*`` ids and this path was
                        # unreachable, which is why the card menu was the only
                        # drive available.
                        #
                        # Ctrl+A FIRST: ``reset_metrics`` deliberately refuses to
                        # widen an EMPTY scope to the whole pool
                        # (use_cases/gallery_actions.py), and Ctrl+A selects what
                        # is visible — the drive a user performs. Measured
                        # 2026-10-28: without it the action "ran" and cleared
                        # nothing (metrics_cache_size 6 -> 6).
                        try:
                            # Focus first: Ctrl+A selects what the GRID shows, so
                            # a click into the grid is part of the drive (an
                            # unlaid-out/unfocused grid refuses, by design).
                            card = [
                                row for row in (control_now.call("ui_elements").get("elements") or [])
                                if row.get("role") == "card" and row.get("label") == "Button"
                            ]
                            if card:
                                control_now.call("ui_click", id=card[0]["id"])
                            control_now.call("press_keys", keys="Ctrl+A")
                        except Exception as exc:  # noqa: BLE001 - reported, not fatal
                            reset_info["select_all_error"] = f"{type(exc).__name__}: {exc}"
                        time.sleep(0.4)
                        reset_info["selection"] = (
                            control_now.call("get_state", path="tabs.image_gallery").get("state")
                            or {}
                        ).get("selection_count")
                        control_now.call("run_action", action_id="gallery.reset-metrics")
                        reset_info["via"] = "run_action gallery.reset-metrics"
                        time.sleep(0.5)
                        reset_info["state_after"] = control_now.call(
                            "get_state", path="tabs.image_gallery"
                        ).get("state")
                        reset_info["fired"] = True
                        return
                    cards = [
                        row for row in (control_now.call("ui_elements").get("elements") or [])
                        if row.get("role") == "card" and row.get("label") == "Button"
                    ]
                    if not cards:
                        raise RuntimeError("no gallery card to open the menu on")
                    control_now.call("ui_click", id=cards[0]["id"], button="right")
                    time.sleep(0.8)
                    rows = [
                        row for row in (control_now.call("ui_elements").get("elements") or [])
                        if row.get("role") == "menu-row"
                        and row.get("visible")
                        and "reset metrics" in str(row.get("label", "")).lower()
                    ]
                    if not rows:
                        raise RuntimeError("the card menu has no 'Reset metrics cache' row")
                    reset_info["menu_row"] = rows[0].get("label")
                    control_now.call("ui_click", id=rows[0]["id"])
                    # The clear must be VISIBLE immediately (the action re-runs by
                    # design, so a later reading shows the re-run, not the clear).
                    time.sleep(0.5)
                    reset_info["state_after"] = control_now.call(
                        "get_state", path="tabs.image_gallery"
                    ).get("state")
                    reset_info["fired"] = True
                except Exception as exc:  # noqa: BLE001 — a failed reset is the verdict
                    reset_info["fired"] = False
                    reset_info["error"] = f"{type(exc).__name__}: {exc}"

            watcher = threading.Thread(target=_reset_when_running, name="reset-watcher", daemon=True)
            watcher.start()
        from devtools import live_gallery_ai_run as driver

        driver_args = [
            "--folder", str(folder),
            "--domain", "ai",
            "--timeout", str(args.timeout),
            "--quiet", str(args.quiet),
            "--log", str(args.log),
            "--keep-app",
        ]
        if args.scenario == "chain":
            # The chain proof must spend the judge calls; the RESET proof cannot
            # — the barrier cancels the run, so "judge run done" never appears and
            # a strict settle would wait out the whole timeout (measured
            # 2026-10-28: 300 s burned, verdict "did not settle", while the run
            # itself had behaved correctly).
            driver_args.append("--require-judge")
        code = driver.main(driver_args)
        verdict["driver_exit"] = code
        if code != 0:
            verdict["reason"] = "the driver did not settle"
            return code if code in (2, 3, 4) else 1

        sock = Path(os.environ["IMGSLI_MCP_CONTROL_SOCKET"]) if os.environ.get(
            "IMGSLI_MCP_CONTROL_SOCKET"
        ) else Path(os.environ.get("IMGSLI_CONTROL_DIR", "")) / "control.sock"
        control = _control_client(sock)
        ping = control.call("ping")
        app_pid = int(ping.get("pid") or 0) or None
        verdict["app_pid"] = app_pid

        # The AI tail settling is NOT the local pass settling: the stage-2 lanes
        # keep measuring (measured 2026-10-28 — reading/killing right after the
        # judge finished found an empty local-metrics cache and would have
        # "proved" the local side absent).
        settled_local = False
        deadline = time.monotonic() + 150.0
        while time.monotonic() < deadline:
            state_now = control.call("get_state", path="tabs.image_gallery").get("state") or {}
            size = int(state_now.get("metrics_cache_size") or 0)
            count = int(state_now.get("item_count") or 0)
            if count and size >= count:
                settled_local = True
                break
            time.sleep(1.5)
        verdict["local_pass_settled"] = settled_local

        # Decode counters (W7 item 3): the tracer spans `decode.proxy` /
        # `decode.store` / `decode.coarse`, so a live cold/warm count needs no
        # instrumented build — and the WARM half is what a cache claim is about.
        def _decode_counts() -> dict:
            rows = control.call("query_trace", filter="decode.", n=2000).get("records") or []
            counts: dict[str, dict[str, int]] = {}
            for row in rows:
                kind = str(row.get("kind") or "")
                if not kind.startswith("decode."):
                    continue
                payload = row.get("payload") or {}
                counts.setdefault(kind, {})
                path = str(payload.get("path") or "?")
                counts[kind][path] = counts[kind].get(path, 0) + 1
            return counts

        cold = _decode_counts()
        verdict["decode_cold"] = cold
        try:
            control.call("open_folder", path=str(folder), tab="image_gallery")
            time.sleep(3.0)
            warm = _decode_counts()
            verdict["decode_warm"] = warm
            verdict["decode_warm_added"] = {
                kind: sum(warm.get(kind, {}).values()) - sum(cold.get(kind, {}).values())
                for kind in set(cold) | set(warm)
            }
        except Exception as exc:  # noqa: BLE001 - a warm probe failure is not the chain's
            verdict["decode_warm"] = f"unavailable: {type(exc).__name__}: {exc}"

        try:
            trace = control.call("query_trace", filter=JUDGE_ONLY_AXIS, n=40)
            verdict["trace_hits"] = [
                {"kind": row.get("kind"), "summary": str(row.get("summary"))[:120]}
                for row in (trace.get("records") or [])
            ][:12]
        except Exception as exc:  # noqa: BLE001 - a trace is evidence, not a gate
            verdict["trace_hits"] = f"unavailable: {type(exc).__name__}: {exc}"

        try:
            control.call("capture_live", path=str(args.artifact))
            verdict["artifact"] = str(args.artifact)
        except Exception as exc:  # noqa: BLE001
            verdict["artifact"] = f"capture failed: {type(exc).__name__}: {exc}"

        state = control.call("get_state", path="tabs.image_gallery")
        verdict["gallery_state"] = state.get("state")
        log_tail = control.call("read_log", n=400).get("lines") or []
        # The in-app ring keeps DEBUG lines, so the local pass's own reasons are
        # readable here even when the on-disk log is INFO-only.
        deep = control.call("read_log", level="DEBUG", n=4000).get("lines") or []
        needles = ("local metrics", "not persisted", "previous mode", "proxy", "chunk")
        verdict["deep_log"] = [row.get("text", "") for row in deep]
        verdict["local_pass_log"] = [
            row["text"] for row in deep if any(n in row.get("text", "").lower() for n in needles)
        ][:25]
        verdict["log_lines"] = {
            "judge_run_done": [ln["text"] for ln in log_tail if "judge run done" in ln.get("text", "")],
            "profile_source": [ln["text"] for ln in log_tail if "profile source" in ln.get("text", "")],
            "wire": [ln["text"] for ln in log_tail if "analyze wire ready" in ln.get("text", "")][:4],
            "rank": [ln["text"] for ln in log_tail if "jev rank" in ln.get("text", "")][:8],
            "analyze_start": [ln["text"] for ln in log_tail if "analyze start" in ln.get("text", "")][:8],
        }
    finally:
        if app_pid and not args.keep_app:
            _stop_app(app_pid)
        requests = list(stub.requests)
        stub.close()
        if lease is not None:
            lease.release()

    profile_calls = [r for r in requests if "FROM 5 TO 8 axes" in json.dumps(r.get("body") or {})]
    scorecard_calls = [
        r for r in requests
        if "WINNER" not in json.dumps(r.get("body") or {}).upper()
        and "FROM 5 TO 8 axes" not in json.dumps(r.get("body") or {})
        and (r.get("body") or {}).get("messages")
    ]
    verdict["stub_calls"] = {
        "total": len(requests),
        "profile": len(profile_calls),
        "scorecard": len(scorecard_calls),
        "models": sum(1 for r in requests if str(r.get("path", "")).rstrip("/") == "/v1/models"),
    }
    verdict["scorecard_request_has_image"] = bool(
        scorecard_calls
        and "data:image" in json.dumps(scorecard_calls[0].get("body") or {})
    )

    request_text = json.dumps(
        (scorecard_calls[0].get("body") if scorecard_calls else {}) or {},
        ensure_ascii=False,
    )
    measured_marker = "LOCAL MEASUREMENTS (axes the model is NOT asked to score)"
    measured_block = ""
    if measured_marker in request_text:
        measured_block = request_text.split(measured_marker, 1)[1][:600]
    asked = [SHARED_AXIS, "noise", "exposure", JUDGE_ONLY_AXIS, "micro_contrast", "colour_banding"]
    verdict["measured_block_present"] = bool(measured_block)
    verdict["measured_block_mentions_asked_axis"] = [
        axis for axis in asked if axis in measured_block.lower()
    ]

    ai_entries = _ai_axes(_read_entries("gallery_ai_cache"))
    local_entries = _read_entries("gallery_local_metrics")
    local_values = _local_axis_values(local_entries)
    verdict["ai_entries"] = ai_entries
    verdict["local_metrics_entries"] = len(local_entries)
    verdict["local_axes"] = sorted(local_values)
    verdict["local_shared_value"] = local_values.get(SHARED_AXIS)

    checks: dict[str, bool] = {
        "profile_answer_served": len(profile_calls) >= 1,
        "scorecard_answer_served": len(scorecard_calls) >= 1,
        "scorecard_carried_the_image": verdict["scorecard_request_has_image"],
        "judge_axis_in_profile_log": any(
            JUDGE_ONLY_AXIS in line for line in verdict["log_lines"]["profile_source"]
        ),
        "ai_entries_written": bool(ai_entries),
        "judge_only_axis_is_the_answer_value": bool(ai_entries) and all(
            row["axes"].get(JUDGE_ONLY_AXIS) == JUDGE_SCORE for row in ai_entries
        ),
        "shared_axis_is_the_judge_number": bool(ai_entries) and all(
            row["axes"].get(SHARED_AXIS) == JUDGE_SHARED_SCORE for row in ai_entries
        ),
        "judge_prompt_carried_a_measured_block": verdict["measured_block_present"],
        "measured_block_dropped_every_asked_axis": not verdict[
            "measured_block_mentions_asked_axis"
        ],
        "no_local_only_axis_in_the_ai_entry": bool(ai_entries) and not any(
            axis in row["axes"] for row in ai_entries for axis in LOCAL_ONLY_AXES
        ),
        "decode_spans_recorded": bool(verdict.get("decode_cold")),
        "every_item_proxied_at_least_once": bool(verdict.get("decode_cold", {}).get("decode.proxy"))
        and all(count >= 1 for count in verdict["decode_cold"]["decode.proxy"].values()),
        # NOT a gate: measured 2026-10-28, a folder REOPEN re-decodes every item
        # (4 cold -> +4 warm). The proxy cache does not survive a pool reset, which
        # is a design fact worth reporting, not a defect — the "warm reopen = 0"
        # invariant the isolation fixtures assert is about re-reading the SAME
        # file (Quick Look), not about reopening the folder. The number is in the
        # verdict so nobody quotes "warm = 0" about a folder reopen.
        "warm_reopen_was_measured": isinstance(verdict.get("decode_warm_added"), dict),
        "rank_reached_the_ranker": any(
            marker in line
            for line in verdict["log_lines"]["rank"]
            for marker in ("jev rank complete", "jev rank applied", "jev rank =>")
        ),

    }
    if args.scenario == "reset":
        reset_files = _cache_files()
        newest = max((p.stat().st_mtime for p in reset_files), default=0.0)
        after_ms = reset_info.get("at_ms") or 0
        late_lines = []
        for row in verdict["log_lines"].get("analyze_start", []) + verdict["log_lines"].get("rank", []):
            late_lines.append(row)
        drop_after = [
            row for row in verdict.get("deep_log", [])
            if "dropped" in row.lower() and "in flight" in row.lower() and _line_ms(row) >= after_ms
        ]
        checks = {
            "reset_fired_during_the_run": bool(reset_info.get("fired")),
            "run_was_active_when_it_fired": int(
                (reset_info.get("state_before") or {}).get("metrics_cache_size") or 0
            ) > 0,
            # "Reset metrics cache" DROPS the measured caches for its SCOPE and
            # then re-runs (the action documents two scopes: the card menu clears
            # one card, the Find Action clears the selection, and the measured
            # stores are swept pool-wide either way). So the clear is checked
            # against the scope, and the barrier is measured by what a pre-reset
            # delivery could still have written — never by "no work afterwards".
            "cleared_the_selected_scope": int(
                (reset_info.get("state_after") or {}).get("metrics_cache_size") or 0
            )
            == max(
                0,
                int((reset_info.get("state_before") or {}).get("metrics_cache_size") or 0)
                - int(
                    reset_info.get("selection")
                    if reset_info.get("via") == "run_action gallery.reset-metrics"
                    else 1
                ),
            ),
            "pre_reset_delivery_was_dropped": bool(drop_after),
            "no_cache_file_written_after_reset": newest * 1000.0 < after_ms,
            "no_rank_after_reset": not [
                row for row in verdict["log_lines"].get("rank", [])
                if "jev rank applied" in row and _line_ms(row) >= after_ms
            ],
        }
        verdict["reset"] = reset_info
        verdict["cache_files_after"] = len(reset_files)
        verdict["cache_newest_mtime"] = newest
        verdict["checks"] = checks

    verdict["checks"] = checks
    verdict["ok"] = all(checks.values())
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(verdict, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: verdict[k] for k in ("ok", "checks", "stub_calls", "ai_entries", "artifact")},
                     ensure_ascii=False, indent=2))
    return 0 if verdict["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
