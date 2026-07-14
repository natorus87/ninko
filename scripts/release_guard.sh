#!/usr/bin/env bash
# Release-Guard: verhindert Builds/Deploys aus einem falschen oder veralteten
# Git-Stand. Hintergrund: v1.5.3 wurde aus einem main gebaut, dem 179 Commits
# des Feature-Branchs fehlten — das deployte Image verlor still Features und
# Security-Fixes (siehe CHANGELOG 1.5.4).
#
# Verwendung (Pflicht vor jedem Prod-Build, siehe .claude/skills/ninko-deploy):
#   ./scripts/release_guard.sh          # alle Checks
#   ./scripts/release_guard.sh --dev    # nur Branch-/Sauberkeits-Checks (Dev-Build)
set -euo pipefail

cd "$(git rev-parse --show-toplevel)"

DEV_MODE=false
[ "${1:-}" = "--dev" ] && DEV_MODE=true

fail() { echo "❌ RELEASE-GUARD: $1" >&2; exit 1; }
ok() { echo "✅ $1"; }

# 1. Sauberes Arbeitsverzeichnis
if [ -n "$(git status --porcelain)" ]; then
  fail "Arbeitsverzeichnis nicht sauber — committe oder stashe zuerst:
$(git status --short | head -10)"
fi
ok "Arbeitsverzeichnis sauber"

# 2. Auf main
BRANCH=$(git rev-parse --abbrev-ref HEAD)
if [ "$BRANCH" != "main" ]; then
  fail "Nicht auf main (aktuell: $BRANCH). Prod-Builds nur aus main."
fi
ok "Branch: main"

# 3. Up to date mit origin/main
git fetch origin main --quiet
LOCAL=$(git rev-parse main)
REMOTE=$(git rev-parse origin/main)
if [ "$LOCAL" != "$REMOTE" ]; then
  BEHIND=$(git rev-list --count main..origin/main)
  AHEAD=$(git rev-list --count origin/main..main)
  fail "main und origin/main sind auseinander (ahead: $AHEAD, behind: $BEHIND). Erst pull/push."
fi
ok "main == origin/main ($(git rev-parse --short main))"

if [ "$DEV_MODE" = true ]; then
  echo "🟡 Dev-Modus: Versions-/Branch-Merge-Checks übersprungen."
  exit 0
fi

# 4. Keine nicht gemergten Remote-Branches mit Commits, die main fehlen
#    (gh-pages ist Doku, kein Code-Branch)
UNMERGED=""
while read -r ref; do
  short=${ref#origin/}
  case "$short" in main|HEAD|gh-pages) continue ;; esac
  count=$(git rev-list --count "main..$ref")
  [ "$count" -gt 0 ] && UNMERGED="$UNMERGED  $short ($count Commits nicht in main)\n"
done < <(git branch -r --format='%(refname:short)')
if [ -n "$UNMERGED" ]; then
  fail "Nicht gemergte Remote-Branches gefunden — prüfen, ob deren Stand ins Release gehört:
$(printf '%b' "$UNMERGED")Wenn bewusst ausgeschlossen: Branch löschen oder Guard mit --dev umgehen (nur Dev)."
fi
ok "Keine nicht gemergten Remote-Branches"

# 5. VERSION muss neuer sein als der letzte Release-Tag (sonst wurde der Bump vergessen)
VERSION=$(tr -d '[:space:]' < VERSION)
LAST_TAG=$(git tag -l 'v*' --sort=-v:refname | head -1)
if [ -n "$LAST_TAG" ]; then
  if [ "v$VERSION" = "$LAST_TAG" ]; then
    if git rev-parse -q --verify "refs/tags/v$VERSION" >/dev/null && \
       [ "$(git rev-parse "v$VERSION^{commit}")" != "$(git rev-parse HEAD)" ]; then
      fail "VERSION ($VERSION) entspricht dem letzten Tag ($LAST_TAG), aber HEAD ist nicht der getaggte Commit. VERSION bumpen (+ CHANGELOG) oder vom Tag bauen."
    fi
    ok "VERSION $VERSION == Tag $LAST_TAG und HEAD ist der getaggte Commit (Re-Build eines Releases)"
  else
    HIGHEST=$(printf '%s\n' "v$VERSION" "$LAST_TAG" | sort -V | tail -1)
    if [ "$HIGHEST" != "v$VERSION" ]; then
      fail "VERSION ($VERSION) ist älter als der letzte Tag ($LAST_TAG). VERSION bumpen."
    fi
    ok "VERSION $VERSION > letzter Tag $LAST_TAG"
  fi
fi

echo "🟢 Release-Guard bestanden — Build aus $(git rev-parse --short HEAD) freigegeben."
