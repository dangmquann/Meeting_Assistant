#!/bin/bash
# Start ALL services (Full Option C Architecture)
# Core + Streaming + Processing + Vector + CDC + Analytics + Orchestration
# Usage: ./scripts/start-full-stack.sh

echo "🚀 Starting FULL STACK (Option C)..."
echo "⚠️  This requires ~16GB RAM!"
echo ""

docker-compose \
  -f docker-compose.yml \
  -f docker-compose.streaming.yml \
  -f docker-compose.processing.yml \
  -f docker-compose.vector.yml \
  -f docker-compose.cdc.yml \
  -f docker-compose.analytics.yml \
  -f docker-compose.orchestration.yml \
  up -d

echo "✅ Full stack started!"
echo ""
echo "📊 Available dashboards:"
echo "   - Kafka UI: http://localhost:8081"
echo "   - Flink JobManager: http://localhost:8082"
echo "   - Spark Master: http://localhost:8083"
echo "   - Qdrant: http://localhost:6333/dashboard"
echo "   - Trino: http://localhost:8080"
echo "   - MinIO: http://localhost:9001"
echo "   - Airflow: http://localhost:9090"
echo ""
echo "📡 Service endpoints:"
echo "   - MongoDB: localhost:27017"
echo "   - PostgreSQL: localhost:5434"
echo "   - Kafka: localhost:9092 (internal) / localhost:29092 (external)"
echo "   - Qdrant HTTP: localhost:6333"
echo "   - Spark Master: spark://localhost:7077"
echo "   - Debezium Connect: http://localhost:8083"
echo "   - Trino: localhost:8080"

