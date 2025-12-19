#!/bin/bash
set -e

# TinyOlly Release Script
# Creates git tag, pushes to remote, and creates GitHub release
#
# Usage: ./release.sh <version>
# Example: ./release.sh v2.0.0

VERSION=${1:-""}

if [ -z "$VERSION" ]; then
    echo "Error: Version is required"
    echo "Usage: ./release.sh <version>"
    echo "Example: ./release.sh v2.0.0"
    exit 1
fi

# Validate version format
if [[ ! "$VERSION" =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    echo "Error: Version must be in format vX.Y.Z (e.g., v2.0.0)"
    exit 1
fi

echo "=========================================="
echo "TinyOlly Release: $VERSION"
echo "=========================================="
echo ""

# Check if tag already exists locally
if git rev-parse "$VERSION" >/dev/null 2>&1; then
    echo "Tag $VERSION already exists locally"
else
    # Check release notes exist
    RELEASE_NOTES="release-notes/RELEASE-NOTES-$VERSION.md"
    if [ ! -f "$RELEASE_NOTES" ]; then
        echo "Error: Release notes file '$RELEASE_NOTES' not found"
        exit 1
    fi

    echo "Creating git tag $VERSION..."
    git tag -a "$VERSION" -m "Release $VERSION"
    echo "Created tag $VERSION"
fi
echo ""

# Push tag to remote
echo "Pushing tag to origin..."
git push origin "$VERSION"
echo "Pushed tag $VERSION"
echo ""

# Create GitHub release
RELEASE_NOTES="release-notes/RELEASE-NOTES-$VERSION.md"
if [ -f "$RELEASE_NOTES" ]; then
    echo "Creating GitHub release..."
    if gh release view "$VERSION" >/dev/null 2>&1; then
        echo "GitHub release $VERSION already exists"
    else
        gh release create "$VERSION" --title "TinyOlly $VERSION" --notes-file "$RELEASE_NOTES"
        echo "Created GitHub release $VERSION"
    fi
else
    echo "Warning: No release notes found at $RELEASE_NOTES"
    echo "Creating GitHub release without notes..."
    if gh release view "$VERSION" >/dev/null 2>&1; then
        echo "GitHub release $VERSION already exists"
    else
        gh release create "$VERSION" --title "TinyOlly $VERSION" --generate-notes
        echo "Created GitHub release $VERSION"
    fi
fi
echo ""

echo "=========================================="
echo "Release $VERSION Complete!"
echo "=========================================="
echo ""
echo "View release: https://github.com/tinyolly/tinyolly/releases/tag/$VERSION"
echo ""
