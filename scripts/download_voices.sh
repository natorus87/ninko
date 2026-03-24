#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────────────
# Kumio TTS – Piper Stimmen & Binary herunterladen
#
# Lädt folgende deutsche Stimmen von HuggingFace herunter:
#   - de_DE-thorsten-medium   (männlich, gute Qualität, ~65 MB)
#   - de_DE-kerstin-low       (weiblich, klein, ~25 MB)
#   - de_DE-eva_k-x_low       (weiblich, sehr klein, ~5 MB)
#
# Und (optional) das Piper-Binary für Linux x86_64 von GitHub Releases.
#
# Verwendung:
#   ./scripts/download_voices.sh [--voices-dir ./data/voices] [--skip-piper]
#
# Voraussetzungen: curl, unzip (nur für Piper-Binary)
# ──────────────────────────────────────────────────────────────────────────────

set -euo pipefail

# ── Standardwerte ──────────────────────────────────────────────────────────
VOICES_DIR="${VOICES_DIR:-./data/voices}"
SKIP_PIPER=false
PIPER_VERSION="1.2.0"
PIPER_ARCH="linux_x86_64"

# ── Argumente parsen ────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
    case $1 in
        --voices-dir)  VOICES_DIR="$2"; shift 2 ;;
        --skip-piper)  SKIP_PIPER=true; shift ;;
        --piper-version) PIPER_VERSION="$2"; shift 2 ;;
        -h|--help)
            grep '^#' "$0" | grep -v '!/usr/bin' | sed 's/^# \{0,2\}//'
            exit 0
            ;;
        *) echo "Unbekannte Option: $1" >&2; exit 1 ;;
    esac
done

HF_BASE="https://huggingface.co/rhasspy/piper-voices/resolve/main"
PIPER_RELEASE_URL="https://github.com/rhasspy/piper/releases/download/${PIPER_VERSION}/piper_${PIPER_ARCH}.tar.gz"

# ── Hilfsfunktionen ──────────────────────────────────────────────────────────

log() { echo "[$(date '+%H:%M:%S')] $*"; }
ok()  { echo "[$(date '+%H:%M:%S')] ✓ $*"; }
err() { echo "[$(date '+%H:%M:%S')] ✗ $*" >&2; }

download_file() {
    local url="$1"
    local dest="$2"
    local desc="${3:-$dest}"

    if [[ -f "$dest" ]]; then
        log "Bereits vorhanden: $desc – überspringe."
        return 0
    fi

    local dest_dir
    dest_dir="$(dirname "$dest")"
    mkdir -p "$dest_dir"

    log "Lade herunter: $desc …"
    if curl -fsSL --progress-bar -o "$dest" "$url"; then
        local size
        size=$(du -sh "$dest" | cut -f1)
        ok "Heruntergeladen: $desc ($size)"
    else
        err "Fehler beim Herunterladen: $url"
        rm -f "$dest"
        return 1
    fi
}

download_voice() {
    local lang="$1"
    local voice_name="$2"
    local hf_path="$3"
    local desc="$4"

    log "──────────────────────────────────────────────"
    log "Stimme: $desc ($lang/$voice_name)"

    local voice_dir="$VOICES_DIR/$lang/$voice_name"
    local file_stem
    file_stem="$(basename "$hf_path")"

    download_file \
        "$HF_BASE/${hf_path}.onnx" \
        "$voice_dir/${file_stem}.onnx" \
        "${file_stem}.onnx" || return 1

    download_file \
        "$HF_BASE/${hf_path}.onnx.json" \
        "$voice_dir/${file_stem}.onnx.json" \
        "${file_stem}.onnx.json" || return 1

    ok "Stimme '$voice_name' bereit in: $voice_dir"
}

# ── Piper-Binary installieren ────────────────────────────────────────────────

install_piper() {
    if command -v piper &>/dev/null; then
        ok "Piper bereits im PATH: $(which piper)"
        return 0
    fi

    local install_dir="/usr/local/bin"
    local piper_bin="$install_dir/piper"

    if [[ -f "$piper_bin" ]]; then
        ok "Piper bereits installiert: $piper_bin"
        return 0
    fi

    log "──────────────────────────────────────────────"
    log "Piper-Binary v${PIPER_VERSION} für ${PIPER_ARCH} herunterladen …"

    if ! command -v curl &>/dev/null; then
        err "curl nicht gefunden. Bitte curl installieren."
        return 1
    fi

    local tmp_dir
    tmp_dir="$(mktemp -d)"
    trap "rm -rf '$tmp_dir'" EXIT

    local tar_file="$tmp_dir/piper.tar.gz"

    log "URL: $PIPER_RELEASE_URL"
    if ! curl -fsSL --progress-bar -o "$tar_file" "$PIPER_RELEASE_URL"; then
        err "Download fehlgeschlagen: $PIPER_RELEASE_URL"
        return 1
    fi

    log "Entpacke Piper …"
    tar -xzf "$tar_file" -C "$tmp_dir"

    # Piper-Binary liegt in piper/piper (oder direkt als piper)
    local extracted_bin
    extracted_bin=$(find "$tmp_dir" -name "piper" -type f | head -1)

    if [[ -z "$extracted_bin" ]]; then
        err "Piper-Binary nicht im Archiv gefunden."
        return 1
    fi

    # libonnxruntime mitkopieren (Piper-Dependency)
    local lib_file
    lib_file=$(find "$tmp_dir" -name "libonnxruntime*.so*" | head -1)
    if [[ -n "$lib_file" ]]; then
        cp "$lib_file" "$install_dir/" 2>/dev/null || true
        log "libonnxruntime nach $install_dir kopiert."
    fi

    cp "$extracted_bin" "$piper_bin"
    chmod +x "$piper_bin"

    ok "Piper installiert: $piper_bin"
    piper --version 2>&1 || true
}

# ── Hauptprogramm ─────────────────────────────────────────────────────────────

echo ""
echo "═══════════════════════════════════════════════════════"
echo "  Kumio TTS – Piper Stimmen herunterladen"
echo "  Zielverzeichnis: $VOICES_DIR"
echo "═══════════════════════════════════════════════════════"
echo ""

mkdir -p "$VOICES_DIR"

# Piper-Binary
if [[ "$SKIP_PIPER" == "false" ]]; then
    install_piper || log "HINWEIS: Piper-Binary konnte nicht installiert werden (ggf. Root-Rechte nötig). Manuell installieren: https://github.com/rhasspy/piper/releases"
else
    log "Piper-Binary-Installation übersprungen (--skip-piper)."
fi

# Deutsche Stimmen
# Format: download_voice <lang> <voice-dir-name> <hf-subpath> <beschreibung>

download_voice \
    "de" \
    "thorsten-medium" \
    "de/de_DE/thorsten/medium/de_DE-thorsten-medium" \
    "Thorsten (männlich, mittel)"

download_voice \
    "de" \
    "kerstin-low" \
    "de/de_DE/kerstin/low/de_DE-kerstin-low" \
    "Kerstin (weiblich, klein)"

download_voice \
    "de" \
    "eva_k-x_low" \
    "de/de_DE/eva_k/x_low/de_DE-eva_k-x_low" \
    "Eva K (weiblich, sehr klein)"

download_voice \
    "de" \
    "ramona-low" \
    "de/de_DE/ramona/low/de_DE-ramona-low" \
    "Ramona (weiblich, klein)"

echo ""
echo "═══════════════════════════════════════════════════════"
echo "  Fertig!"
echo ""
echo "  Stimmen in: $VOICES_DIR"
echo ""
echo "  Kumio TTS aktivieren in docker-compose.yml / k8s:"
echo "    TTS_ENABLED: \"true\""
echo "    VOICES_DIR: \"/app/data/voices\""
echo "    TTS_DEFAULT_LANG: \"de\""
echo "    TTS_DEFAULT_VOICE: \"thorsten-medium\""
echo ""
echo "  Stimme testen:"
echo "    echo 'Hallo, ich bin Kumio.' | piper \\"
echo "      --model $VOICES_DIR/de/thorsten-medium/*.onnx \\"
echo "      --output_file /tmp/test.wav && aplay /tmp/test.wav"
echo "═══════════════════════════════════════════════════════"
echo ""
