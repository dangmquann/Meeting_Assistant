#!/bin/bash
# Start full streaming pipeline
# Core + Streaming + Processing + Vector
# Usage: ./scripts/start-streaming-pipeline.sh

echo "🚀 Starting FULL STREAMING PIPELINE..."
docker-compose \
  -f docker-compose.yml \
  -f docker-compose.streaming.yml \
  -f docker-compose.processing.yml \
  -f docker-compose.vector.yml \
  up -d

echo "✅ Streaming pipeline started!"
echo ""
echo "📊 Available dashboards:"
echo "   - Kafka UI: http://localhost:8081"
echo "   - Flink JobManager: http://localhost:8082"
echo "   - Spark Master: http://localhost:8083"
echo "   - Qdrant: http://localhost:6333/dashboard"
echo "   - MinIO: http://localhost:9001"
echo ""
echo "📡 Service endpoints:"
echo "   - MongoDB: localhost:27017"
echo "   - PostgreSQL: localhost:5434"
echo "   - Kafka: localhost:9092 (internal) / localhost:29092 (external)"
echo "   - Qdrant HTTP: localhost:6333"
echo "   - Spark Master: spark://localhost:7077"

