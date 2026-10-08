#!/usr/bin/env python3
"""Pit-side Meshtastic receiver bridge for PitFUSION opponent intel."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import threading
import time
import zlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, List, Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    load_dotenv = None

try:
    from pubsub import pub
    from meshtastic.serial_interface import SerialInterface
except ImportError:  # pragma: no cover
    pub = None
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


def _parse_iso(ts: Optional[str]) -> Optional[datetime]:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None


@dataclass
class BridgeConfig:
    bridge_host: str = os.getenv("BRIDGE_HOST", "127.0.0.1")
    bridge_port: int = _int_env("BRIDGE_PORT", 8090)
    pit_team_number: str = os.getenv("PIT_TEAM_NUMBER", "88").strip()
    tba_key: str = os.getenv("TBA_KEY", "").strip()
    tba_event_key: str = os.getenv("TBA_EVENT_KEY", "").strip().lower()
    hmac_secret: str = os.getenv("INTEL_HMAC_SECRET", "").strip()
    meshtastic_port: str = os.getenv("MESHTASTIC_PORT", "").strip()
    intel_max_age_seconds: int = _int_env("INTEL_MAX_AGE_SECONDS", 900)
    tba_refresh_seconds: int = _int_env("TBA_REFRESH_SECONDS", 30)
    simulator_mode: bool = _bool_env("BRIDGE_SIMULATOR_MODE", False)
    simulator_interval_seconds: int = _int_env("BRIDGE_SIMULATOR_INTERVAL_SECONDS", 20)


@dataclass
class BridgeState:
    lock: threading.Lock = field(default_factory=threading.Lock)
    raw_payload: Optional[Dict[str, Any]] = None
    normalized_payload: Optional[Dict[str, Any]] = None
    available: bool = False
    reason: str = "no_payload"
    status: str = "unavailable"
    last_packet_at: Optional[str] = None
    last_valid_packet_at: Optional[str] = None
    last_signature_valid: bool = False
    last_signature_error: Optional[str] = None
    current_match_key: Optional[str] = None
    current_event_key: Optional[str] = None
    tba_next_match_key: Optional[str] = None
    last_tba_refresh_at: Optional[str] = None


class TBAClient:
    def __init__(self, config: BridgeConfig):
        self.config = config
        self._cache: Dict[str, Any] = {"event": None, "matches": [], "at": 0.0}

    def _headers(self) -> Dict[str, str]:
        return {"X-TBA-Auth-Key": self.config.tba_key} if self.config.tba_key else {}

    def _fetch_matches(self) -> List[Dict[str, Any]]:
        if not (self.config.tba_key and self.config.tba_event_key):
            return []

        now = time.time()
        if now - self._cache["at"] <= self.config.tba_refresh_seconds:
            return self._cache["matches"]

        url = f"https://www.thebluealliance.com/api/v3/event/{self.config.tba_event_key}/matches/simple"
        req = Request(url, headers=self._headers())
        with urlopen(req, timeout=12) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        if isinstance(data, list):
            self._cache = {"event": self.config.tba_event_key, "matches": data, "at": now}
            return data
        return []

    def next_match(self) -> Optional[Dict[str, Any]]:
        try:
            matches = self._fetch_matches()
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError):
            return None

        team_key = f"frc{self.config.pit_team_number}"
        upcoming = []
        for m in matches:
            if m.get("actual_time") is not None:
                continue
            red = m.get("alliances", {}).get("red", {}).get("team_keys", [])
            blue = m.get("alliances", {}).get("blue", {}).get("team_keys", [])
            if team_key not in red and team_key not in blue:
                continue
            score_order = m.get("predicted_time") or m.get("time") or m.get("match_number") or 0
            upcoming.append((score_order, m))

        if not upcoming:
            return None

        upcoming.sort(key=lambda x: x[0])
        return upcoming[0][1]


class IntelBridge:
    def __init__(self, config: BridgeConfig):
        self.config = config
        self.state = BridgeState()
        self.tba = TBAClient(config)
        self._iface = None

    @staticmethod
    def _canonical(obj: Dict[str, Any]) -> str:
        return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)

    def _verify_signature(self, payload: Dict[str, Any], sig_hex: str) -> Tuple[bool, Optional[str]]:
        if not self.config.hmac_secret:
            return False, "missing_hmac_secret"
        if not sig_hex:
            return False, "missing_signature"

        digest = hmac.new(
            self.config.hmac_secret.encode("utf-8"),
            self._canonical(payload).encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(digest, sig_hex), None

    @staticmethod
    def _normalize_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
        # Accept compact sender schema and expanded schema.
        opponents_in = payload.get("op") if "op" in payload else payload.get("opponents", [])
        opponents: List[Dict[str, Any]] = []
        for item in opponents_in[:3]:
            team = item.get("t") if "t" in item else item.get("team")
            summary = item.get("s") if "s" in item else item.get("summary")
            tags = item.get("tg") if "tg" in item else item.get("tags", [])
            notes = item.get("n") if "n" in item else item.get("notes", "")
            if team is None:
                continue
            opponents.append(
                {
                    "team": str(team),
                    "summary": str(summary or "No summary"),
                    "tags": [str(x) for x in (tags or [])][:4],
                    "notes": str(notes or ""),
                }
            )

        return {
            "schemaVersion": int(payload.get("sv") or payload.get("schemaVersion") or 1),
            "generatedAt": payload.get("ga") or payload.get("generatedAt"),
            "expiresAt": payload.get("ea") or payload.get("expiresAt"),
            "eventKey": (payload.get("ev") or payload.get("eventKey") or "").lower(),
            "matchKey": payload.get("mk") or payload.get("matchKey") or "",
            "opponents": opponents,
        }

    def _decode_envelope_payload(self, envelope: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        enc = envelope.get("encoding") or envelope.get("enc") or "json"
        if enc == "json":
            payload = envelope.get("payload")
            return payload if isinstance(payload, dict) else None
        if enc == "zlib-base64":
            encoded = envelope.get("payload")
            if not isinstance(encoded, str):
                return None
            raw = zlib.decompress(base64.b64decode(encoded.encode("ascii"))).decode("utf-8")
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else None
        return None

    def ingest_envelope(self, envelope: Dict[str, Any]) -> None:
        payload = self._decode_envelope_payload(envelope)
        sig = envelope.get("sig") or envelope.get("signature") or ""

        with self.state.lock:
            self.state.last_packet_at = _utc_iso()

        if not payload:
            with self.state.lock:
                self.state.available = False
                self.state.reason = "invalid_payload"
                self.state.status = "unavailable"
                self.state.last_signature_valid = False
                self.state.last_signature_error = "decode_failed"
                self.state.raw_payload = None
                self.state.normalized_payload = None
            return

        sig_ok, sig_error = self._verify_signature(payload, str(sig))
        normalized = self._normalize_payload(payload)

        with self.state.lock:
            self.state.last_signature_valid = sig_ok
            self.state.last_signature_error = None if sig_ok else (sig_error or "signature_mismatch")
            if not sig_ok:
                self.state.available = False
                self.state.reason = self.state.last_signature_error
                self.state.status = "unavailable"
                self.state.raw_payload = None
                self.state.normalized_payload = None
                return

            self.state.raw_payload = payload
            self.state.normalized_payload = normalized
            self.state.last_valid_packet_at = _utc_iso()

        self.recompute_status()

    def recompute_status(self) -> None:
        next_match = self.tba.next_match()
        next_key = next_match.get("key") if next_match else None

        with self.state.lock:
            self.state.tba_next_match_key = next_key
            self.state.last_tba_refresh_at = _utc_iso()
            payload = self.state.normalized_payload

            if not payload:
                self.state.available = False
                self.state.reason = "no_payload"
                self.state.status = "unavailable"
                return

            if payload.get("schemaVersion") != 1:
                self.state.available = False
                self.state.reason = "unsupported_schema"
                self.state.status = "unavailable"
                self.state.normalized_payload = None
                self.state.raw_payload = None
                return

            generated_at = _parse_iso(payload.get("generatedAt"))
            expires_at = _parse_iso(payload.get("expiresAt"))
            now = datetime.now(timezone.utc)

            if generated_at is None:
                self.state.available = False
                self.state.reason = "invalid_generated_at"
                self.state.status = "unavailable"
                self.state.normalized_payload = None
                self.state.raw_payload = None
                return

            age_sec = (now - generated_at).total_seconds()
            if age_sec > self.config.intel_max_age_seconds:
                self.state.available = False
                self.state.reason = "stale_payload"
                self.state.status = "unavailable"
                self.state.normalized_payload = None
                self.state.raw_payload = None
                return

            if expires_at and now >= expires_at:
                self.state.available = False
                self.state.reason = "expired_payload"
                self.state.status = "unavailable"
                self.state.normalized_payload = None
                self.state.raw_payload = None
                return

            if not next_key:
                self.state.available = False
                self.state.reason = "no_next_match"
                self.state.status = "unavailable"
                self.state.normalized_payload = None
                self.state.raw_payload = None
                return

            if payload.get("matchKey") != next_key:
                self.state.available = False
                self.state.reason = "match_mismatch"
                self.state.status = "unavailable"
                self.state.normalized_payload = None
                self.state.raw_payload = None
                return

            if self.config.tba_event_key and payload.get("eventKey") != self.config.tba_event_key:
                self.state.available = False
                self.state.reason = "event_mismatch"
                self.state.status = "unavailable"
                self.state.normalized_payload = None
                self.state.raw_payload = None
                return

            self.state.available = True
            self.state.reason = "ok"
            self.state.status = "ready"
            self.state.current_event_key = payload.get("eventKey")
            self.state.current_match_key = payload.get("matchKey")

    def to_response(self) -> Dict[str, Any]:
        self.recompute_status()
        with self.state.lock:
            payload = self.state.normalized_payload if self.state.available else None
            return {
                "available": self.state.available,
                "status": self.state.status,
                "reason": self.state.reason,
                "bridgeTime": _utc_iso(),
                "lastPacketAt": self.state.last_packet_at,
                "lastValidPacketAt": self.state.last_valid_packet_at,
                "lastSignatureValid": self.state.last_signature_valid,
                "lastSignatureError": self.state.last_signature_error,
                "eventKey": self.state.current_event_key,
                "matchKey": self.state.current_match_key,
                "tbaNextMatchKey": self.state.tba_next_match_key,
                "payload": payload,
                "opponents": (payload or {}).get("opponents", []),
            }

    def _on_receive(self, packet: Dict[str, Any], _interface: Any) -> None:
        try:
            decoded = packet.get("decoded", {}) if isinstance(packet, dict) else {}
            text = decoded.get("text")
            if not text:
                return
            envelope = json.loads(text)
            if not isinstance(envelope, dict):
                return
            if envelope.get("type") != "pitfusion_next_match_intel_v1":
                return
            self.ingest_envelope(envelope)
        except Exception:
            with self.state.lock:
                self.state.available = False
                self.state.reason = "packet_parse_error"
                self.state.status = "unavailable"

    def _simulator_loop(self) -> None:
        while True:
            next_match = self.tba.next_match()
            if next_match:
                sample_teams = [88, 1768, 6328, 2056, 125]
                sample_teams = [t for t in sample_teams if str(t) != self.config.pit_team_number][:3]
                sample_rows = [
                    {"t": sample_teams[0], "s": "Auto high, fast cycles", "tg": ["fast-cycler"], "n": "Watch source lane"},
                    {"t": sample_teams[1], "s": "Defense capable", "tg": ["defense"], "n": "Force traffic"},
                    {"t": sample_teams[2], "s": "Elite auto", "tg": ["high-endgame"], "n": "Primary threat"},
                ]
                payload = {
                    "sv": 1,
                    "ga": _utc_iso(),
                    "ea": _utc_iso(time.time() + 600),
                    "ev": self.config.tba_event_key,
                    "mk": next_match.get("key"),
                    "op": sample_rows,
                }
                sig = hmac.new(
                    self.config.hmac_secret.encode("utf-8"),
                    self._canonical(payload).encode("utf-8"),
                    hashlib.sha256,
                ).hexdigest() if self.config.hmac_secret else ""
                self.ingest_envelope({"type": "pitfusion_next_match_intel_v1", "encoding": "json", "payload": payload, "sig": sig})
            time.sleep(max(5, self.config.simulator_interval_seconds))

    def connect_meshtastic(self) -> None:
        if self.config.simulator_mode:
            threading.Thread(target=self._simulator_loop, daemon=True).start()
            return

        if pub is None or SerialInterface is None:
            with self.state.lock:
                self.state.reason = "meshtastic_dependency_missing"
            return

        iface = SerialInterface(devPath=self.config.meshtastic_port or None)
        pub.subscribe(self._on_receive, "meshtastic.receive")
        self._iface = iface

    def close(self) -> None:
        if self._iface is not None:
            try:
                self._iface.close()
            except Exception:
                pass


class BridgeHandler(BaseHTTPRequestHandler):
    bridge: IntelBridge = None  # type: ignore

    def _write_json(self, code: int, obj: Dict[str, Any]) -> None:
        body = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        if self.path in {"/api/next-match-intel", "/api/health"}:
            self._write_json(200, self.bridge.to_response())
            return
        self._write_json(404, {"error": "not_found"})

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/api/simulate":
            self._write_json(404, {"error": "not_found"})
            return

        try:
            size = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(size) if size > 0 else b"{}"
            envelope = json.loads(raw.decode("utf-8"))
            if not isinstance(envelope, dict):
                raise ValueError("invalid JSON object")
            self.bridge.ingest_envelope(envelope)
            self._write_json(200, {"ok": True})
        except Exception as exc:
            self._write_json(400, {"ok": False, "error": str(exc)})

    def log_message(self, *_args: Any) -> None:
        return


def main() -> None:
    if load_dotenv is not None:
        load_dotenv()

    config = BridgeConfig()
    bridge = IntelBridge(config)
    bridge.connect_meshtastic()

    BridgeHandler.bridge = bridge
    server = ThreadingHTTPServer((config.bridge_host, config.bridge_port), BridgeHandler)

    print(
        f"[PitFUSION Bridge] listening on http://{config.bridge_host}:{config.bridge_port}"
        f" | simulator={config.simulator_mode}"
    )

    try:
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        bridge.close()


if __name__ == "__main__":
    main()
