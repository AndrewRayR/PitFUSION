# PitFusion

A real-time FRC pit display that fuses [Nexus](https://frc.nexus/) and
[The Blue Alliance](https://www.thebluealliance.com/) into one screen — live queuing,
countdown, bumper color, rankings, alerts, pit map, EPA stats, Lovat opponent intel, and the event livestream.

Single HTML file, no framework, no build step.

## Use it

**[pitfusion.com](https://pitfusion.com)** — nothing to install or configure. Runs on a
Cloudflare Worker; API keys are held server-side, so nothing sensitive is in the page.

## Run your own copy

Download or clone the repository and run **`public/Start PitFUSION.bat`** on Windows. It
starts the local web server and the optional Lovat/Meshtastic bridge. On first launch,
open **⚙ Settings** and enter your own Nexus and Blue Alliance API keys (a YouTube Data
API key is optional — it's only used to auto-detect a live webcast). Browser keys are stored
only in localStorage; bridge and sender secrets belong in the ignored **`.env`** file.

Full guide: **[docs/self-hosting.md](docs/self-hosting.md)**.

## Repository layout

| Path | What it is |
|------|------------|
| `public/` | Static assets served directly by the Worker — `index.html` (the whole app), `config.js` (non-secret config only), images, `_headers`. |
| `worker.js` | The Cloudflare Worker. Runs only for `/api/*` (`run_worker_first`); proxies `/api/nexus/*`, `/api/tba/*`, `/api/youtube/*` to the real APIs, injecting keys from secrets. |
| `wrangler.toml`, `.dev.vars.example` | Worker config; the three hosted secrets are `NEXUS_API_KEY`, `TBA_API_KEY`, `YOUTUBE_API_KEY`. |
| `tools/` | Lovat/Meshtastic pit-side bridge, internet-side sender, and Python dependencies. |
| `.env.example` | Example bridge/sender environment configuration; copy to `.env` and keep `.env` uncommitted. |
| `docs/` | Self-hosting guide, custom-theme guide, the hosting-migration design doc. |

One codebase runs both ways: it detects **hosted** mode on `pitfusion.com` / `*.workers.dev`
(calls go through the proxy) and **self-hosted** mode everywhere else (calls go direct
with your keys).

## Lovat / Meshtastic Opponent Intel

PitFUSION's Lovat integration adds a dedicated **Lovat** tab with opponent intel for
up to the next three matches, pinned strategy notes, an optional five-minute-before-queue
popup, and a post-qualification alliance-captain tracker. The integration supports two
sources: a local **Meshtastic bridge** (the default) and an optional internet endpoint.

### Meshtastic setup

1. Copy **`.env.example`** to **`.env`**.
2. Set `TBA_KEY`, `TBA_EVENT_KEY`, `PIT_TEAM_NUMBER`, and a random `INTEL_HMAC_SECRET`.
3. Set `MESHTASTIC_PORT` to the serial port used by the pit-side Meshtastic node.
4. Install the bridge dependencies with `python -m pip install -r tools/requirements.txt`.
5. Start **`public/Start PitFUSION.bat`**. The bridge listens on
   `http://localhost:8090/api/next-match-intel` and the web app listens on port 8080.

For an internet-connected sender node, configure `LOVAT_API_KEY` and
`LOVAT_EXPORT_URL` in its private `.env`, then run `python tools/lovat_mesh_sender.py`.
The sender expects the configured Lovat export to return an `opponents` array (or a list
of opponent rows). It signs payloads before sending them over Meshtastic, and the bridge
rejects stale, mismatched, or invalidly signed payloads.

The frontend `public/config.js` contains only non-secret Lovat settings. Do **not** put a
real Lovat API key in that file; `.env` is ignored by Git for bridge/sender secrets.

### Simulator mode

The bridge and sender include simulator switches for testing without a live radio. Use
`BRIDGE_SIMULATOR_MODE=true` for the pit-side bridge and, on the sender node,
`SENDER_SIMULATOR_MODE=true` plus `SENDER_SIMULATOR_NO_RADIO=true` to exercise the
transport and validation logic without Meshtastic hardware.

## Credits

Powered by [The Blue Alliance](https://www.thebluealliance.com/) · data from
[Nexus](https://frc.nexus/) · EPA from [Statbotics](https://www.statbotics.io/) ·
Lovat opponent intelligence via the optional Meshtastic bridge · inspired by
[Pulse](https://pulsefrc.app/). Home team: [Team 88 TJ²](https://www.tj2.org/).

## License

[MIT](LICENSE).
