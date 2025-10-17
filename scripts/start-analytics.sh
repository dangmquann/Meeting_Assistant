#!/bin/bash
# Start analytics stack
# Core + Analytics (Trino + Hive)
# Usage: ./scripts/start-analytics.sh

echo "🚀 Starting ANALYTICS STACK..."
docker-compose \
  -f docker-compose.yml \
  -f docker-compose.analytics.yml \
  up -d

echo "✅ Analytics stack started!"
echo ""
echo "📊 Available dashboards:"
echo "   - Trino: http://localhost:8080"
echo "   - MinIO: http://localhost:9001"
echo ""
echo "📡 Service endpoints:"
echo "   - MongoDB: localhost:27017"
echo "   - PostgreSQL: localhost:5434"
echo "   - Trino: localhost:8080"
echo "   - Hive Metastore: localhost:9083"
echo "   - MinIO S3: localhost:9000"

