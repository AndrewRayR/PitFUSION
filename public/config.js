// ============================================================
//  PitFUSION Configuration — non-secret settings only.
//  Place this file in the same folder as index.html
//
//  API keys are NOT set here. Enter them in the app's Settings
//  panel (the gear icon) when self-hosting; hosted deployments
//  read them from server-side environment variables.
// ============================================================

// ── Hosting mode override (optional) ─────────────────────────
// Leave commented for auto-detection (hosted on *.pitfusion.com /
// *.pages.dev, self-hosted everywhere else). Uncomment to force:
// const FORCE_MODE = 'selfhosted';   // or 'hosted'

// ── Lovat / Meshtastic Opponent Intel (frontend-safe) ─────────
// The Lovat API key is intentionally NOT stored in this public file.
// Configure internet mode in a private/self-hosted environment only.
// Meshtastic is the default because the included local bridge needs no browser secret.
const LOVAT_INTEL_ENABLED = true;
const LOVAT_INTEL_SOURCE_DEFAULT = 'meshtastic'; // 'internet' or 'meshtastic'
const LOVAT_INTEL_ENDPOINT = 'http://localhost:8090/api/next-match-intel';
const LOVAT_INTEL_INTERNET_ENDPOINT = '';
const LOVAT_KEY = '';
const LOVAT_INTEL_POLL_MS = 10000;

// ── EPA Field Definitions by Year ────────────────────────────
// Which EPA components the EPA Stats overlay charts, per season.
//
//   key   — Statbotics per-match EPA field, from
//           /v3/matches → m.epas["<team>"].<key>
//           (the app maps it to the matching team_year.epa.breakdown.<field>
//            for the "current value" marker — see SB_YEAR_FIELD in index.html)
//   label — display label
//   color — line colour (any CSS colour)
//
// The core fields are year-agnostic: `epa` (total), `auto_epa`, `teleop_epa`,
// `endgame_epa`, `rp_1_epa`, `rp_2_epa`, `rp_3_epa`. For a new season the only
// change is usually the RP labels (each game names its ranking points differently).
//
// The same /v3/matches response also carries a per-match `pred` object
// (win probability + predicted score) — consumed by the opt-in match-predictions
// feature (⚙ Settings ▸ Display). Nothing to configure here for that.
const EPA_FIELDS = {
  2026: [
    { key: 'epa',         label: 'Total EPA',       color: '#00d4ff' },
    { key: 'auto_epa',    label: 'Auto EPA',        color: '#00e676' },
    { key: 'teleop_epa',  label: 'Teleop EPA',      color: '#ffd600' },
    { key: 'endgame_epa', label: 'Endgame EPA',     color: '#ff6b35' },
    { key: 'rp_1_epa',    label: 'Energized RP',    color: '#a78bfa' },
    { key: 'rp_2_epa',    label: 'Supercharged RP', color: '#f472b6' },
  ],
  2025: [
    { key: 'epa',         label: 'Total EPA',   color: '#00d4ff' },
    { key: 'auto_epa',    label: 'Auto EPA',    color: '#00e676' },
    { key: 'teleop_epa',  label: 'Teleop EPA',  color: '#ffd600' },
    { key: 'endgame_epa', label: 'Endgame EPA', color: '#ff6b35' },
    { key: 'rp_1_epa',    label: 'Coral RP',    color: '#a78bfa' },
    { key: 'rp_2_epa',    label: 'Barge RP',    color: '#f472b6' },
  ],
  // Add future years here — copy the block above and rename the RP labels.
};
