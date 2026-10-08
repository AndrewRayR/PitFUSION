#!/usr/bin/env python3
"""Internet-side Lovat -> Meshtastic sender for PitFUSION opponent intel."""

from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import os
import time
import zlib
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from urllib.request import Request, urlopen

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    load_dotenv = None

try:
    from meshtastic.serial_interface import SerialInterface
except ImportError:  # pragma: no cover
    SerialInterface = None


def _bool_env(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)).strip())
    except Exception:
        return default


def _utc_iso(ts: Optional[float] = None) -> str:
    dt = datetime.fromtimestamp(ts or time.time(), tz=timezone.utc)
    return dt.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def canonical(obj: Dict[str, Any]) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


class SenderConfig:
    pit_team_number: str = os.getenv("PIT_TEAM_NUMBER", "88").strip()
    tba_key: str = os.getenv("TBA_KEY", "").strip()
    tba_event_key: str = os.getenv("TBA_EVENT_KEY", "").strip().lower()
    lovat_api_key: str = os.getenv("LOVAT_API_KEY", "").strip()
    lovat_export_url: str = os.getenv("LOVAT_EXPORT_URL", "").strip()
    hmac_secret: str = os.getenv("INTEL_HMAC_SECRET", "").strip()
    meshtastic_port: str = os.getenv("MESHTASTIC_PORT", "").strip()
    meshtastic_channel_index: int = _int_env("MESHTASTIC_CHANNEL_INDEX", 0)
    trigger_matches_before: int = _int_env("INTEL_TRIGGER_MATCHES_BEFORE", 2)
    burst_interval_seconds: int = _int_env("INTEL_BURST_INTERVAL_SECONDS", 20)
    burst_duration_seconds: int = _int_env("INTEL_BURST_DURATION_SECONDS", 120)
    steady_interval_seconds: int = _int_env("INTEL_STEADY_INTERVAL_SECONDS", 60)
    max_payload_bytes: int = _int_env("MESHTASTIC_MAX_PAYLOAD_BYTES", 220)
    poll_seconds: int = _int_env("SENDER_POLL_SECONDS", 10)
    simulator_mode: bool = _bool_env("SENDER_SIMULATOR_MODE", False)
    simulator_no_radio: bool = _bool_env("SENDER_SIMULATOR_NO_RADIO", False)


def api_get_json(url: str, headers: Optional[Dict[str, str]] = None) -> Any:
    req = Request(url, headers=headers or {})
    with urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


def get_tba_matches(config: SenderConfig) -> List[Dict[str, Any]]:
    url = f"https://www.thebluealliance.com/api/v3/event/{config.tba_event_key}/matches/simple"
    headers = {"X-TBA-Auth-Key": config.tba_key}
    data = api_get_json(url, headers=headers)
    return data if isinstance(data, list) else []


def schedule_context(config: SenderConfig) -> Tuple[Optional[Dict[str, Any]], Optional[int]]:
    matches = get_tba_matches(config)
    team_key = f"frc{config.pit_team_number}"

    upcoming_all = []
    for m in matches:
        if m.get("actual_time") is not None:
            continue
        if m.get("comp_level") == "qm":
            order = m.get("match_number") or 999999
        else:
            order = (m.get("predicted_time") or m.get("time") or 0) + 1_000_000
        upcoming_all.append((order, m))

    if not upcoming_all:
        return None, None

    upcoming_all.sort(key=lambda x: x[0])
    upcoming_matches = [m for _, m in upcoming_all]

    my_upcoming = []
    for m in upcoming_matches:
        red = m.get("alliances", {}).get("red", {}).get("team_keys", [])
        blue = m.get("alliances", {}).get("blue", {}).get("team_keys", [])
        if team_key in red or team_key in blue:
            my_upcoming.append(m)

    if not my_upcoming:
        return None, None

    my_next = my_upcoming[0]
    idx = next((i for i, m in enumerate(upcoming_matches) if m.get("key") == my_next.get("key")), None)
    return my_next, idx


def parse_lovat_opponents(raw: Any, opponent_teams: List[str]) -> List[Dict[str, Any]]:
    if isinstance(raw, dict) and isinstance(raw.get("opponents"), list):
        src = raw.get("opponents")
    elif isinstance(raw, list):
        src = raw
    else:
        src = []

    parsed: Dict[str, Dict[str, Any]] = {}
    for row in src:
        if not isinstance(row, dict):
            continue
        team = str(row.get("team") or row.get("teamNumber") or row.get("team_key") or "").replace("frc", "")
        if not team:
            continue
        parsed[team] = {
            "t": int(team),
            "s": str(row.get("summary") or row.get("intel") or "Scouting summary unavailable"),
            "tg": [str(x) for x in (row.get("tags") or [])][:4],
            "n": str(row.get("notes") or ""),
        }

    result: List[Dict[str, Any]] = []
    for team in opponent_teams:
        if team in parsed:
            result.append(parsed[team])
        else:
            result.append(
                {
                    "t": int(team),
                    "s": "Scouting data unavailable",
                    "tg": ["missing"],
                    "n": "No Lovat export row for this team",
                }
            )
    return result[:3]


def fetch_lovat_opponents(config: SenderConfig, event_key: str, match_key: str, opponent_teams: List[str]) -> List[Dict[str, Any]]:
    if config.simulator_mode or not config.lovat_export_url:
        return [
            {"t": int(opponent_teams[0]), "s": "Auto high, fast cycles", "tg": ["fast-cycler"], "n": "Protect source lane"},
            {"t": int(opponent_teams[1]), "s": "Defense capable", "tg": ["defense"], "n": "Force congestion"},
            {"t": int(opponent_teams[2]), "s": "Strong endgame", "tg": ["high-endgame"], "n": "Primary threat"},
        ]

    url = config.lovat_export_url.format(
        event_key=event_key,
        match_key=match_key,
        teams=",".join(opponent_teams),
    )
    headers = {"Authorization": "Bearer " + config.lovat_api_key} if config.lovat_api_key else {}

    try:
        raw = api_get_json(url, headers=headers)
        return parse_lovat_opponents(raw, opponent_teams)
    except Exception:
        return parse_lovat_opponents({}, opponent_teams)


def build_payload(config: SenderConfig, next_match: Dict[str, Any], opponents: List[Dict[str, Any]]) -> Dict[str, Any]:
    event_key = config.tba_event_key
    match_key = next_match.get("key")
    predicted = next_match.get("predicted_time") or next_match.get("time") or int(time.time())

    expires_at = predicted + 60
    payload = {
        "sv": 1,
        "ga": _utc_iso(),
        "ea": _utc_iso(expires_at),
        "ev": event_key,
        "mk": match_key,
        "op": opponents[:3],
    }
    return payload


def sign_payload(config: SenderConfig, payload: Dict[str, Any]) -> str:
    return hmac.new(
        config.hmac_secret.encode("utf-8"),
        canonical(payload).encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def encode_envelope(config: SenderConfig, payload: Dict[str, Any]) -> Dict[str, Any]:
    sig = sign_payload(config, payload)
    compressed = base64.b64encode(zlib.compress(canonical(payload).encode("utf-8"), level=9)).decode("ascii")
    envelope = {
        "type": "pitfusion_next_match_intel_v1",
        "enc": "zlib-base64",
        "payload": compressed,
        "sig": sig,
    }

    body = json.dumps(envelope, separators=(",", ":"))
    if len(body.encode("utf-8")) <= config.max_payload_bytes:
        return envelope

    # Fallback to plain JSON payload when compression metadata exceeds envelope limits.
    fallback = {
        "type": "pitfusion_next_match_intel_v1",
        "enc": "json",
        "payload": payload,
        "sig": sig,
    }
    return fallback


def opponent_teams_for_match(config: SenderConfig, next_match: Dict[str, Any]) -> List[str]:
    my = f"frc{config.pit_team_number}"
    red = [t.replace("frc", "") for t in next_match.get("alliances", {}).get("red", {}).get("team_keys", [])]
    blue = [t.replace("frc", "") for t in next_match.get("alliances", {}).get("blue", {}).get("team_keys", [])]
    if my in next_match.get("alliances", {}).get("red", {}).get("team_keys", []):
        return blue[:3]
    return red[:3]


def should_send_for_match(config: SenderConfig, idx_to_next: int) -> bool:
    return idx_to_next is not None and idx_to_next <= config.trigger_matches_before


def transmit(iface: Optional[Any], config: SenderConfig, envelope: Dict[str, Any]) -> None:
    text = json.dumps(envelope, separators=(",", ":"))
    if config.simulator_no_radio or iface is None:
        print(f"[SIM SEND] {text}")
        return
    iface.sendText(text, channelIndex=config.meshtastic_channel_index, wantAck=False)


def run(config: SenderConfig, once: bool = False) -> None:
    if not config.tba_key:
        raise RuntimeError("TBA_KEY is required")
    if not config.tba_event_key:
        raise RuntimeError("TBA_EVENT_KEY is required")
    if not config.hmac_secret:
        raise RuntimeError("INTEL_HMAC_SECRET is required")

    iface = None
    if not config.simulator_no_radio:
        if SerialInterface is None:
            raise RuntimeError("meshtastic dependency missing. Install meshtastic package.")
        iface = SerialInterface(devPath=config.meshtastic_port or None)

    active_match_key = None
    first_sent_at = 0.0
    last_sent_at = 0.0

    print("[PitFUSION Sender] running")

    try:
        while True:
            now = time.time()
            try:
                next_match, idx = schedule_context(config)
            except Exception as exc:
                print(f"[WARN] Failed to read TBA schedule: {exc}")
                if once:
                    break
                time.sleep(config.poll_seconds)
                continue

            if not next_match or idx is None or not should_send_for_match(config, idx):
                if once:
                    break
                time.sleep(config.poll_seconds)
                continue

            match_key = next_match.get("key")
            if match_key != active_match_key:
                active_match_key = match_key
                first_sent_at = 0.0
                last_sent_at = 0.0

            interval = config.burst_interval_seconds if (first_sent_at and now - first_sent_at <= config.burst_duration_seconds) else config.steady_interval_seconds
            if last_sent_at and (now - last_sent_at) < interval:
                if once:
                    break
                time.sleep(config.poll_seconds)
                continue

            opponents = opponent_teams_for_match(config, next_match)
            if len(opponents) < 3:
                if once:
                    break
                time.sleep(config.poll_seconds)
                continue

            intel_rows = fetch_lovat_opponents(config, config.tba_event_key, match_key, opponents)
            payload = build_payload(config, next_match, intel_rows)
            envelope = encode_envelope(config, payload)

            transmit(iface, config, envelope)
            print(f"[SEND] match={match_key} opponents={','.join(opponents)} idxToNext={idx}")

            if first_sent_at == 0.0:
                first_sent_at = now
            last_sent_at = now

            if once:
                break

            time.sleep(config.poll_seconds)
    finally:
        if iface is not None:
            iface.close()


def main() -> None:
    if load_dotenv is not None:
        load_dotenv()

    parser = argparse.ArgumentParser(description="PitFUSION Lovat Meshtastic sender")
    parser.add_argument("--once", action="store_true", help="Run a single send attempt")
    parser.add_argument("--simulate", action="store_true", help="Force simulator mode")
    parser.add_argument("--simulate-no-radio", action="store_true", help="Print packets instead of sending to Meshtastic")
    args = parser.parse_args()

    config = SenderConfig()
    if args.simulate:
        config.simulator_mode = True
    if args.simulate_no_radio:
        config.simulator_no_radio = True

    run(config, once=args.once)


if __name__ == "__main__":
    main()
