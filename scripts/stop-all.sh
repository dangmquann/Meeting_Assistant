#!/bin/bash
# Stop ALL services
# Usage: ./scripts/stop-all.sh

echo "🛑 Stopping all services..."

docker-compose \
  -f docker-compose.yml \
  -f docker-compose.streaming.yml \
  -f docker-compose.processing.yml \
  -f docker-compose.vector.yml \
  -f docker-compose.cdc.yml \
  -f docker-compose.analytics.yml \
  -f docker-compose.orchestration.yml \
  down

echo "✅ All services stopped!"

