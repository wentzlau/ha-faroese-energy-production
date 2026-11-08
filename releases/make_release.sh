#!/usr/bin/env bash
#
# Prepare a HACS release for the "Faroese energy production" integration.
#
# HACS is configured with "zip_release": true in hacs.json, which means HACS
# downloads a zip asset attached to a GitHub release and extracts it straight
# into config/custom_components/<domain>/. The zip must therefore contain the
# integration files (python code, manifest.json, strings, translations) at its
# ROOT, and be named exactly like the "filename" field in hacs.json.
#
# Usage:
#   releases/make_release.sh [VERSION] [--tag] [--publish]
#
#   VERSION    Release version, e.g. 1.0.3 (a leading "v" is stripped).
#              Defaults to the version currently in manifest.json.
#   --tag      Commit the manifest version bump (if any) and create git tag VERSION.
#   --publish  Implies --tag. Pushes the commit + tag and creates a GitHub
#              release with the zip attached (requires the gh CLI).
#
# Output:
#   releases/dist/<filename from hacs.json>
#
set -euo pipefail

# --- locate paths -----------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
HACS_JSON="${REPO_ROOT}/hacs.json"
DIST_DIR="${SCRIPT_DIR}/dist"

die()  { echo "ERROR: $*" >&2; exit 1; }
info() { echo "==> $*"; }

command -v python3 >/dev/null || die "python3 is required"
command -v zip     >/dev/null || die "zip is required"

# Small helper: read a top-level key from a JSON file using python (no jq needed)
json_get() {
    python3 -I -c 'import json,sys; print(json.load(open(sys.argv[1]))[sys.argv[2]])' "$1" "$2"
}

# --- parse arguments --------------------------------------------------------
VERSION=""
DO_TAG=false
DO_PUBLISH=false
for arg in "$@"; do
    case "$arg" in
        --tag)      DO_TAG=true ;;
        --publish)  DO_TAG=true; DO_PUBLISH=true ;;
        -h|--help)  sed -n '2,24p' "$0"; exit 0 ;;
        -*)         die "Unknown option: $arg" ;;
        *)          [[ -z "$VERSION" ]] || die "Version given twice"; VERSION="${arg#v}" ;;
    esac
done

# --- find the integration ---------------------------------------------------
[[ -f "$HACS_JSON" ]] || die "hacs.json not found at $HACS_JSON"

shopt -s nullglob
COMPONENTS=("${REPO_ROOT}"/custom_components/*/manifest.json)
shopt -u nullglob
[[ ${#COMPONENTS[@]} -eq 1 ]] || die "Expected exactly one integration in custom_components/, found ${#COMPONENTS[@]}"

MANIFEST="${COMPONENTS[0]}"
COMPONENT_DIR="$(dirname "$MANIFEST")"
DOMAIN="$(json_get "$MANIFEST" domain)"
ZIP_NAME="$(json_get "$HACS_JSON" filename)"
CURRENT_VERSION="$(json_get "$MANIFEST" version)"

[[ "$(basename "$COMPONENT_DIR")" == "$DOMAIN" ]] \
    || die "Folder name '$(basename "$COMPONENT_DIR")' does not match manifest domain '$DOMAIN'"
[[ "$ZIP_NAME" == *.zip ]] || die "hacs.json 'filename' must end with .zip (got '$ZIP_NAME')"

VERSION="${VERSION:-$CURRENT_VERSION}"
[[ "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+([.-][0-9A-Za-z.]+)?$ ]] \
    || die "Version '$VERSION' is not a valid semantic version (e.g. 1.2.3)"

info "Integration : $DOMAIN"
info "Version     : $VERSION (manifest currently $CURRENT_VERSION)"
info "Zip asset   : $ZIP_NAME"

# --- update manifest version --------------------------------------------------
if [[ "$VERSION" != "$CURRENT_VERSION" ]]; then
    info "Updating manifest.json version $CURRENT_VERSION -> $VERSION"
    python3 -I - "$MANIFEST" "$VERSION" <<'PY'
import json, sys
path, version = sys.argv[1], sys.argv[2]
with open(path, encoding="utf-8") as f:
    data = json.load(f)
data["version"] = version
with open(path, "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2, ensure_ascii=False)
    f.write("\n")
PY
fi

# --- validate sources -------------------------------------------------------
info "Validating JSON files"
while IFS= read -r -d '' f; do
    python3 -I -m json.tool "$f" >/dev/null || die "Invalid JSON: ${f#"$REPO_ROOT"/}"
done < <(find "$COMPONENT_DIR" -name '*.json' -not -path '*/__pycache__/*' -print0)

info "Checking required manifest keys"
python3 -I - "$MANIFEST" <<'PY'
import json, sys
data = json.load(open(sys.argv[1]))
missing = [k for k in ("domain", "name", "version", "documentation", "codeowners", "requirements") if k not in data]
if missing:
    sys.exit(f"manifest.json is missing keys: {', '.join(missing)}")
PY

info "Byte-compiling Python files (syntax check)"
while IFS= read -r -d '' f; do
    python3 -I -c 'import ast,sys; ast.parse(open(sys.argv[1], encoding="utf-8").read(), sys.argv[1])' "$f" \
        || die "Syntax error in ${f#"$REPO_ROOT"/}"
done < <(find "$COMPONENT_DIR" -name '*.py' -not -path '*/__pycache__/*' -print0)

# --- build the zip ----------------------------------------------------------
STAGING="$(mktemp -d)"
trap 'rm -rf "$STAGING"' EXIT

info "Staging integration files"
# Copy everything except caches, compiled files and stray archives
( cd "$COMPONENT_DIR" && find . -type f \
      -not -path '*/__pycache__/*' \
      -not -name '*.py[cod]' \
      -not -name '*.zip' \
      -not -name '.DS_Store' \
      -print0 ) \
  | ( cd "$COMPONENT_DIR" && xargs -0 -I{} cp --parents {} "$STAGING/" )

mkdir -p "$DIST_DIR"
ZIP_PATH="${DIST_DIR}/${ZIP_NAME}"
rm -f "$ZIP_PATH"

info "Creating $ZIP_PATH"
# Files at the zip root -> HACS extracts them into custom_components/$DOMAIN/
( cd "$STAGING" && zip -qrX "$ZIP_PATH" . )

echo
echo "Zip contents:"
zip -sf "$ZIP_PATH" | sed -n '2,$p' | sed '$d'
echo

# --- optional: tag & publish ------------------------------------------------
if $DO_TAG; then
    command -v git >/dev/null || die "git is required for --tag"
    cd "$REPO_ROOT"
    git rev-parse --is-inside-work-tree >/dev/null 2>&1 || die "$REPO_ROOT is not a git repository"
    git rev-parse -q --verify "refs/tags/$VERSION" >/dev/null && die "Tag $VERSION already exists"

    if ! git diff --quiet -- "$MANIFEST"; then
        info "Committing manifest version bump"
        git add "$MANIFEST"
        git commit -m "Release $VERSION"
    fi
    info "Creating git tag $VERSION"
    git tag -a "$VERSION" -m "Release $VERSION"
fi

if $DO_PUBLISH; then
    command -v gh >/dev/null || die "gh CLI is required for --publish"
    BRANCH="$(git rev-parse --abbrev-ref HEAD)"
    info "Pushing $BRANCH and tag $VERSION to origin"
    git push origin "$BRANCH"
    git push origin "$VERSION"
    info "Creating GitHub release $VERSION"
    gh release create "$VERSION" "$ZIP_PATH" --title "$VERSION" --generate-notes
fi

info "Done."
if ! $DO_PUBLISH; then
    cat <<EOF

Next steps to publish via HACS:
  1. Commit the manifest change (if any) and create/push tag '$VERSION'
       (or rerun with --tag / --publish)
  2. Create a GitHub release for tag '$VERSION'
  3. Attach: $ZIP_PATH
EOF
fi
