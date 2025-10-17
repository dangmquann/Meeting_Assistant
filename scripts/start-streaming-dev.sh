#!/bin/bash
# Start services for streaming development
# Core + Streaming + Vector
# Usage: ./scripts/start-streaming-dev.sh

echo "🚀 Starting services for STREAMING DEVELOPMENT..."
docker-compose \
  -f docker-compose.yml \
  -f docker-compose.streaming.yml \
  -f docker-compose.vector.yml \
  up -d

echo "✅ Streaming dev services started!"
echo ""
echo "📊 Available dashboards:"
echo "   - Kafka UI: http://localhost:8081"
echo "   - Qdrant: http://localhost:6333/dashboard"
echo "   - MinIO: http://localhost:9001"
echo ""
echo "📡 Service endpoints:"
echo "   - MongoDB: localhost:27017"
echo "   - PostgreSQL: localhost:5434"
echo "   - Kafka: localhost:9092 (internal) / localhost:29092 (external)"
echo "   - Qdrant HTTP: localhost:6333"

