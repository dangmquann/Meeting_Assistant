# Docker Services Documentation

## 📁 Architecture Overview

Dự án được chia thành nhiều docker-compose files theo functional layers để dễ quản lý và scale:

```
docker-compose.yml              # Core services (MongoDB, PostgreSQL, MinIO)
docker-compose.streaming.yml    # Kafka ecosystem (Kafka, Zookeeper, Kafka UI)
docker-compose.processing.yml   # Stream processing (Flink, Spark)
docker-compose.vector.yml       # Vector database (Qdrant)
docker-compose.cdc.yml          # Change Data Capture (Debezium)
docker-compose.analytics.yml    # Data Lake (Trino, Hive Metastore)
docker-compose.orchestration.yml # Workflow (Airflow)
```

## 🚀 Quick Start Scripts

### 1. Core Services Only (~2GB RAM)
```bash
./scripts/start-core.sh
```
Services: MongoDB, PostgreSQL, MinIO

### 2. Streaming Development (~4GB RAM)
```bash
./scripts/start-streaming-dev.sh
```
Services: Core + Kafka + Zookeeper + Kafka UI + Qdrant

### 3. Full Streaming Pipeline (~8GB RAM)
```bash
./scripts/start-streaming-pipeline.sh
```
Services: Core + Streaming + Flink + Spark + Qdrant

### 4. Analytics Stack (~6GB RAM)
```bash
./scripts/start-analytics.sh
```
Services: Core + Trino + Hive Metastore

### 5. Full Stack - Option C (~16GB RAM)
```bash
./scripts/start-full-stack.sh
```
Services: All services combined

### Stop All Services
```bash
./scripts/stop-all.sh
```

### Check Service Status
```bash
./scripts/status.sh
```

## 📊 Service Ports Reference

| Service | Port | Description |
|---------|------|-------------|
| MongoDB | 27017 | Main application database |
| PostgreSQL (offline-fs) | 5434 | Operational database |
| PostgreSQL (metastore) | 5433 | Hive metadata |
| MinIO S3 | 9000 | Object storage API |
| MinIO Console | 9001 | Web UI |
| Zookeeper | 2181 | Kafka coordination |
| Kafka (internal) | 9092 | Internal Kafka broker |
| Kafka (external) | 29092 | External access |
| Kafka UI | 8081 | Kafka monitoring dashboard |
| Flink JobManager | 8082 | Flink Web UI |
| Spark Master UI | 8083 | Spark dashboard |
| Spark Master RPC | 7077 | Spark cluster |
| Debezium Connect | 8083 | CDC REST API |
| Trino | 8080 | Query engine |
| Hive Metastore | 9083 | Metadata service |
| Qdrant HTTP | 6333 | Vector DB REST API |
| Qdrant gRPC | 6334 | Vector DB gRPC |
| Airflow | 9090 | Workflow UI |

## 🎯 Use Case Scenarios

### Scenario 1: Basic Development (Core Only)
```bash
docker-compose up -d
```
- Testing basic API functionality
- Database operations
- File storage operations

### Scenario 2: Streaming Feature Development
```bash
docker-compose -f docker-compose.yml -f docker-compose.streaming.yml -f docker-compose.vector.yml up -d
```
- Developing real-time transcription
- Testing Kafka producers/consumers
- Vector search functionality

### Scenario 3: Testing Full Streaming Pipeline
```bash
docker-compose -f docker-compose.yml -f docker-compose.streaming.yml -f docker-compose.processing.yml -f docker-compose.vector.yml up -d
```
- End-to-end streaming pipeline
- Flink job testing
- Spark streaming jobs
- Vector embeddings

### Scenario 4: CDC & Analytics Testing
```bash
docker-compose -f docker-compose.yml -f docker-compose.streaming.yml -f docker-compose.cdc.yml -f docker-compose.analytics.yml up -d
```
- Change data capture from PostgreSQL
- Data lake operations
- SQL analytics with Trino

### Scenario 5: Production-like Full Stack
```bash
./scripts/start-full-stack.sh
```
- Complete Option C architecture
- All components integrated

## 🔧 Manual Service Control

### Start specific services:
```bash
# Core only
docker-compose up -d

# Core + Streaming
docker-compose -f docker-compose.yml -f docker-compose.streaming.yml up -d

# Add Processing
docker-compose -f docker-compose.yml -f docker-compose.streaming.yml -f docker-compose.processing.yml up -d
```

### Stop specific services:
```bash
# Stop streaming only
docker-compose -f docker-compose.streaming.yml down

# Stop all
docker-compose -f docker-compose.yml -f docker-compose.*.yml down
```

### View logs:
```bash
# All services
docker-compose -f docker-compose.yml -f docker-compose.*.yml logs -f

# Specific service
docker-compose logs -f kafka
docker-compose -f docker-compose.streaming.yml logs -f kafka
```

### Restart a service:
```bash
docker-compose restart kafka
docker-compose -f docker-compose.streaming.yml restart kafka
```

## 📦 Volumes

All persistent data is stored in Docker volumes:

- `mongo_data` - MongoDB database
- `minio_storage` - Object storage
- `kafka_data` - Kafka logs
- `zookeeper_data` - Zookeeper data
- `zookeeper_logs` - Zookeeper logs
- `qdrant_storage` - Vector embeddings
- `flink_checkpoints` - Flink state
- `flink_savepoints` - Flink savepoints
- `spark_master_data` - Spark master data
- `spark_worker_*_data` - Spark worker data
- `airflow_logs` - Airflow logs

### Clean up volumes (⚠️ Deletes all data):
```bash
docker-compose down -v
```

## 🌐 Network

All services communicate through the `rag-network` bridge network. The first `docker-compose up` creates this network, and other compose files reference it as `external: true`.

## 📝 Environment Variables

Services read configuration from `.env` file in the root directory. Make sure to create it:

```bash
cp .env.example .env
# Edit .env with your configurations
```

## 🔍 Troubleshooting

### Service won't start
```bash
# Check logs
docker-compose logs <service-name>

# Check if port is already in use
netstat -tulpn | grep <port>
```

### Network issues
```bash
# Recreate network
docker network rm rag-network
docker-compose up -d
```

### Reset everything
```bash
# Stop all and remove volumes
docker-compose -f docker-compose.yml -f docker-compose.*.yml down -v

# Start fresh
./scripts/start-core.sh
```

## 🎓 Development Workflow

1. **Start with core services:**
   ```bash
   ./scripts/start-core.sh
   ```

2. **Add streaming when developing real-time features:**
   ```bash
   docker-compose -f docker-compose.streaming.yml up -d
   ```

3. **Add processing engines when testing pipelines:**
   ```bash
   docker-compose -f docker-compose.processing.yml up -d
   ```

4. **Scale workers if needed:**
   ```bash
   docker-compose -f docker-compose.processing.yml up -d --scale spark-worker-2=3
   ```

## 📚 Next Steps

After starting services, refer to:
- `/option-c-dual-write.plan.md` - Implementation plan
- `README.md` - Project overview
- Individual service documentation in their respective directories

