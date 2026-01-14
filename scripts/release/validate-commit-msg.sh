#!/usr/bin/env bash
# Validate commit message follows Conventional Commits format
# Install as git hook: ln -s ../../scripts/release/validate-commit-msg.sh .git/hooks/commit-msg

set -euo pipefail

COMMIT_MSG_FILE=$1
COMMIT_MSG=$(cat "$COMMIT_MSG_FILE")

# Skip merge commits
if echo "$COMMIT_MSG" | grep -qE "^Merge "; then
    exit 0
fi

# Skip release-please commits
if echo "$COMMIT_MSG" | grep -qE "^chore\(main\): release"; then
    exit 0
fi

# Conventional commit pattern
PATTERN="^(feat|fix|docs|style|refactor|perf|test|build|ci|chore|revert)(\([a-z0-9\-/,]+\))?!?: .{1,80}$"

if ! echo "$COMMIT_MSG" | head -n1 | grep -qE "$PATTERN"; then
    echo "❌ Invalid commit message format"
    echo ""
    echo "Commit message must follow Conventional Commits:"
    echo "  <type>(<scope>): <description>"
    echo ""
    echo "Examples:"
    echo "  feat(tinyolly): add GenAI span filtering"
    echo "  fix(opamp): handle nil pointer"
    echo "  docs: update API documentation"
    echo ""
    echo "Types: feat, fix, docs, style, refactor, perf, test, build, ci, chore, revert"
    echo "Scopes: tinyolly, opamp, demo, demo-otel-agent, helm/tinyolly, helm/demos, helm/demo-otel-agent"
    echo ""
    echo "Your message:"
    echo "  $COMMIT_MSG"
    exit 1
fi

echo "✅ Commit message valid"
exit 0
