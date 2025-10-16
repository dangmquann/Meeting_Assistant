#!/bin/bash
# Check status of all services
# Usage: ./scripts/status.sh

echo "📊 Service Status:"
echo ""
docker-compose \
  -f docker-compose.yml \
  -f docker-compose.streaming.yml \
  -f docker-compose.processing.yml \
  -f docker-compose.vector.yml \
  -f docker-compose.cdc.yml \
  -f docker-compose.analytics.yml \
  -f docker-compose.orchestration.yml \
  ps

