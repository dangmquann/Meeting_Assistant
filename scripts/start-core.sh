#!/bin/bash
# Start core services only (MongoDB, PostgreSQL, MinIO)
# Usage: ./scripts/start-core.sh

echo "🚀 Starting CORE services..."
docker-compose up -d

echo "✅ Core services started!"
echo "   - MongoDB: localhost:27017"
echo "   - PostgreSQL: localhost:5434"
echo "   - MinIO Console: http://localhost:9001"

