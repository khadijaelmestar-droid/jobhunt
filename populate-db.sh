#!/usr/bin/env bash
set -e

echo "=== Community sources (free, fast) ==="
echo "y" | jobhunt discover

echo ""
echo "=== Perplexity by platform ==="
platforms=(
  greenhouse
  lever
  ashby
  workable
  smartrecruiters
  teamtailor
  recruitee
  personio
  breezy
  jazzhr
  homerun
  bamboohr
)

for p in "${platforms[@]}"; do
  echo "--- $p ---"
  echo "y" | jobhunt discover --source perplexity --platform "$p" || true
done

echo ""
echo "=== Perplexity by MENA region ==="
regions=(morocco mena uae egypt saudi tunisia jordan)

for r in "${regions[@]}"; do
  echo "--- $r ---"
  echo "y" | jobhunt discover --source perplexity --region "$r" || true
done

echo ""
echo "=== Done ==="
jobhunt stats 2>/dev/null || true
