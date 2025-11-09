# ProductForge Backend - Complete Architecture Reference

## 🏗️ System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         Client Layer                            │
│  (Web UI, API consumers, Mobile apps, CLI tools)               │
└───────────────────┬─────────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────────────────────────┐
│                    FastAPI Application                          │
│                   (main_refactored.py)                          │
├─────────────────────────────────────────────────────────────────┤
│  Middleware Stack (executed in order):                          │
│  1. CORSMiddleware - Handle cross-origin requests              │
│  2. Exception Handler - Global error handling                   │
│  3. LoggingMiddleware - Structured access logs                  │
│  4. APIKeyMiddleware - Authentication                           │
└───────────────────┬─────────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────────────────────────┐
│                        Router Layer                             │
├──────────────┬──────────────┬──────────────┬───────────────────┤
│ System       │ Agents       │ Orchestration│ Results           │
│ Routes       │ Routes       │ Routes       │ Routes            │
├──────────────┼──────────────┼──────────────┼───────────────────┤
│ Dashboard    │ Upload       │              │                   │
│ Routes       │ Routes       │              │                   │
└──────┬───────┴──────┬───────┴──────┬───────┴──────┬────────────┘
       │              │              │              │
       ▼              ▼              ▼              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Service Layer                              │
├──────────────┬──────────────┬──────────────┬───────────────────┤
│ Agent        │ Orchestration│ Result       │ Upload            │
│ Service      │ Service      │ Service      │ Service           │
├──────────────┼──────────────┼──────────────┼───────────────────┤
│ Task         │              │              │                   │
│ Service      │              │              │                   │
└──────┬───────┴──────┬───────┴──────┬───────┴──────┬────────────┘
       │              │              │              │
       └──────────────┴──────────────┴──────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────────────────────────┐
│                       Core Layer                                │
├──────────────┬──────────────┬──────────────┬───────────────────┤
│ Redis Client │ OpenAI Client│ Exceptions   │ Utils             │
├──────────────┼──────────────┼──────────────┼───────────────────┤
│ Middleware   │ Auth         │              │                   │
└──────┬───────┴──────┬───────┴──────┬───────┴──────┬────────────┘
       │              │              │              │
       └──────────────┴──────────────┴──────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────────────────────────┐
│                     External Services                           │
├──────────────┬──────────────┬──────────────┬───────────────────┤
│ Redis        │ OpenAI API   │ File System  │ Worker Queue      │
│ (Cache/Queue)│ (LLM)        │ (Uploads/Logs)│ (Background Jobs)│
└──────────────┴──────────────┴──────────────┴───────────────────┘
```

---

## 📁 Directory Structure

```
productforge-backend/
│
├── main.py                      # Thin wrapper for backward compatibility
├── main_refactored.py          # Main FastAPI app with middleware
├── worker.py                    # Background job worker
├── config.py                    # Configuration management
├── models.py                    # Legacy models (being phased out)
│
├── core/                        # Core infrastructure
│   ├── __init__.py
│   ├── redis_client.py         # Redis connection + index helpers
│   ├── openai_client.py        # OpenAI API integration
│   ├── exceptions.py           # Custom exception classes
│   ├── utils.py                # Utility functions
│   ├── middleware.py           # Structured logging middleware
│   └── auth_middleware.py      # API key authentication
│
├── routes/                      # API route definitions
│   ├── __init__.py
│   ├── system_routes.py        # Health, status endpoints
│   ├── agent_routes.py         # Agent management
│   ├── orchestration_routes.py # Workflow orchestration
│   ├── result_routes.py        # Results & exports
│   ├── dashboard_routes.py     # Dashboard UI
│   └── upload_routes.py        # File uploads
│
├── services/                    # Business logic layer
│   ├── __init__.py
│   ├── agent_service.py        # Agent CRUD operations
│   ├── orchestration_service.py # Workflow management
│   ├── result_service.py       # Result storage & retrieval
│   ├── task_service.py         # Task queue management
│   └── upload_service.py       # Upload handling
│
├── models/                      # Pydantic data models
│   ├── __init__.py
│   ├── agent_models.py         # Agent schemas
│   ├── results_models.py       # Result schemas
│   └── task_models.py          # Task schemas
│
├── tests/                       # Test suite
│   ├── __init__.py
│   ├── test_system_health.py   # System health tests
│   ├── test_agents.py          # Agent tests
│   ├── test_orchestration.py   # Orchestration tests
│   ├── test_results.py         # Result tests
│   ├── test_upload.py          # Upload tests
│   ├── test_models.py          # Model validation tests
│   ├── test_config.py          # Configuration tests
│   └── test_integrity.py       # Code integrity tests
│
└── workspace/                   # Runtime data
    ├── logs/                    # Application logs
    │   └── app.log             # Daily rotating logs
    ├── templates/               # HTML templates
    │   ├── dashboard.html      # Main dashboard
    │   └── help.html           # Help page
    └── uploads/                 # Uploaded files
```

---

## 🔑 Redis Key Schema

### Result Keys
```
result:{job_id}              → JSON result document
results_index (ZSET)         → {job_id: timestamp}
```

### Workflow Keys
```
workflow:{workflow_id}       → JSON workflow document
workflows_index (ZSET)       → {workflow_id: timestamp}
```

### Agent Keys
```
agent:{agent_name}           → JSON agent document
agents_index (ZSET)          → {agent_name: created_at}
```

### Upload Keys
```
upload:{upload_id}           → JSON upload metadata
uploads_index (ZSET)         → {upload_id: uploaded_at}
```

### Queue Keys
```
queue                        → List (LPUSH/RPOP) for job queue
queue_high                   → High priority queue
queue_low                    → Low priority queue
worker:heartbeat             → Worker health timestamp
```

---

## 🔄 Request Lifecycle

### 1. Incoming Request
```
Client → FastAPI → CORSMiddleware → ExceptionHandler
  → LoggingMiddleware → APIKeyMiddleware → Router
```

### 2. Route Processing
```
Router → Route Handler → Service Layer → Core/Redis
```

### 3. Response Flow
```
Service → Route Handler → Middleware → Client
(+ Log entry written to workspace/logs/app.log)
```

---

## 🔐 Authentication Flow

### Protected Endpoints (Require X-API-Key)
- `/orchestrate`
- `/workflows`
- `/agents` (POST, DELETE)
- `/results/task`
- `/upload/`

### Public Endpoints (No Auth)
- `/system/health`
- `/dashboard/`
- `/help`

### Authentication Logic
```python
if API_KEY not set:
    # Development mode - no auth
    pass request through
elif path in EXCLUDED_PATHS:
    # Public endpoint
    pass request through
elif X-API-Key header == API_KEY:
    # Valid key
    pass request through
else:
    # Invalid/missing key
    return 401 Unauthorized
```

---

## 📊 Data Flow Examples

### Example 1: Create Workflow
```
POST /orchestrate
  ├─ orchestration_routes.orchestrate()
  │   └─ OrchestrationService.orchestrate_multi_agent()
  │       ├─ Generate workflow_id (UUID)
  │       ├─ Create step jobs (admin → specialist → QA → feedback)
  │       ├─ Enqueue jobs to Redis queue (LPUSH)
  │       ├─ Store workflow doc: workflow:{id}
  │       ├─ Index workflow: ZADD workflows_index
  │       └─ Return response
  └─ LoggingMiddleware logs request
```

### Example 2: Upload File
```
POST /upload/
  ├─ upload_routes.upload_file()
  │   └─ UploadService.upload_file()
  │       ├─ Validate .zip extension
  │       ├─ Generate upload_id (UUID)
  │       ├─ Save to workspace/uploads/{id}_{filename}
  │       ├─ Create analysis job (LPUSH queue)
  │       ├─ Store metadata: upload:{id}
  │       ├─ Index upload: ZADD uploads_index
  │       └─ Return response
  └─ LoggingMiddleware logs request
```

### Example 3: Health Check (Cached)
```
GET /system/health
  ├─ system_routes.system_health()
  │   ├─ Check if cache expired (> 5s)
  │   ├─ If expired:
  │   │   └─ _cached_health_snapshot()
  │   │       ├─ LLEN queue (active jobs)
  │   │       ├─ ZCARD results_index (total results) ← O(1)
  │   │       ├─ Calculate uptime
  │   │       └─ Cache result (lru_cache)
  │   └─ Return cached snapshot
  └─ LoggingMiddleware logs request
```

---

## 🚀 Performance Optimizations

### 1. Redis Indexing
**Before**: SCAN operations O(n)
```python
keys = redis.keys("result:*")  # Blocks, scans all keys
for key in keys:
    result = redis.get(key)
```

**After**: Sorted set indices O(log n + k)
```python
job_ids = redis.zrevrange("results_index", 0, limit-1)  # Fast
pipeline = redis.pipeline()
for job_id in job_ids:
    pipeline.get(f"result:{job_id}")
results = pipeline.execute()
```

### 2. Health Caching
**Before**: Fresh queries every request
```python
@router.get("/health")
def health():
    results = count_all_results()  # Expensive
    jobs = count_active_jobs()     # Expensive
    return {"results": results, "jobs": jobs}
```

**After**: 5-second TTL cache
```python
@lru_cache(maxsize=1)
def _cached_health_snapshot():
    # Computed once every 5s
    return {"results": zcard(), "jobs": llen()}
```

### 3. Streaming Exports
**Before**: Load entire dataset into memory
```python
results = get_all_results()  # Loads everything
json_str = json.dumps(results)
return {"data": json_str}  # Large payload
```

**After**: Generator-based streaming
```python
def _stream_json():
    yield "["
    for i, result in enumerate(results_iterator()):
        if i > 0: yield ","
        yield json.dumps(result)
    yield "]"
return StreamingResponse(_stream_json())
```

---

## 📈 Scalability Considerations

### Horizontal Scaling
- **Stateless app servers**: No local state, all data in Redis
- **Worker scaling**: Multiple workers can pull from shared queue
- **Load balancing**: Standard HTTP load balancer compatible

### Vertical Scaling
- **Redis indices**: Sublinear growth O(log n)
- **Cached health**: Reduces Redis load by ~90%
- **Connection pooling**: Redis client reuses connections

### Resource Limits
- Upload size: 50MB default (configurable)
- Result TTL: 3600s (1 hour, configurable)
- Upload TTL: 7 days (configurable)
- Log rotation: Daily with 7-day retention

---

## 🧪 Testing Strategy

### Unit Tests
```python
# Test individual services in isolation
def test_agent_service_create():
    service = AgentService()
    agent = service.create_agent(...)
    assert agent.name == "test_agent"
```

### Integration Tests
```python
# Test API endpoints with TestClient
def test_orchestrate_endpoint():
    client = TestClient(app)
    response = client.post("/orchestrate", json={...})
    assert response.status_code == 200
```

### End-to-End Tests
```python
# Test complete workflows
def test_workflow_execution():
    # Create workflow
    wf = create_workflow()
    # Wait for completion
    wait_for_status(wf.id, "completed")
    # Verify results
    results = get_workflow_results(wf.id)
    assert len(results) == expected_count
```

---

## 🔍 Monitoring & Observability

### Structured Logging
Every request produces a log line:
```
2025-11-09 15:35:16,062 method=POST path=/orchestrate status=200 duration_ms=2.54 ip=127.0.0.1
```

Fields logged:
- **timestamp**: ISO8601 format
- **method**: HTTP method
- **path**: Request path
- **status**: Response status code
- **duration_ms**: Request duration
- **ip**: Client IP address

### Health Checks
```bash
# Liveness probe
curl http://localhost:8000/system/ping

# Readiness probe
curl http://localhost:8000/system/health
```

### Metrics Available
- Uptime (seconds + human-readable)
- Redis connectivity
- Active job count
- Total result count
- OpenAI API status

---

## 🛠️ Configuration

### Environment Variables
```bash
# Required
REDIS_URL=redis://localhost:6379
OPENAI_API_KEY=sk-...

# Optional
API_KEY=your-secret-key              # Enable auth
PORT=8000                             # Server port
RAILWAY_ENVIRONMENT=production        # Deployment env
MAX_UPLOAD_SIZE=52428800             # 50MB default
```

### Feature Flags
```python
# API key auth (enabled when API_KEY is set)
if os.environ.get("API_KEY"):
    app.add_middleware(APIKeyMiddleware)
```

---

## 📚 API Documentation

### Interactive Docs
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

### OpenAPI Schema
```bash
curl http://localhost:8000/openapi.json
```

---

## 🎯 Best Practices

### Adding New Endpoints
1. Define route in `routes/{module}_routes.py`
2. Implement logic in `services/{module}_service.py`
3. Add data models in `models/{module}_models.py`
4. Write tests in `tests/test_{module}.py`
5. Update this architecture doc

### Adding Redis Indices
1. Define index key in `core/redis_client.py`
2. Add helper functions (index, list, get)
3. Update service layer to use helpers
4. Test with ZCARD/ZREVRANGE operations

### Adding Middleware
1. Create middleware class in `core/`
2. Register **before** routers in `main_refactored.py`
3. Order matters: CORS → Exceptions → Logging → Auth
4. Test with TestClient

---

## 🚀 Deployment Checklist

- [ ] Set `API_KEY` environment variable
- [ ] Configure `REDIS_URL` for production Redis
- [ ] Set `OPENAI_API_KEY` with valid key
- [ ] Set `RAILWAY_ENVIRONMENT=production` (if using Railway)
- [ ] Verify log directory is writable
- [ ] Test health endpoint: `/system/health`
- [ ] Run full test suite: `pytest tests/`
- [ ] Check worker connectivity: `worker:heartbeat` key
- [ ] Configure CORS origins for production domain
- [ ] Enable HTTPS/TLS termination (load balancer)

---

## 📖 Further Reading

- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [Redis Documentation](https://redis.io/docs/)
- [Pydantic Models](https://docs.pydantic.dev/)
- [Pytest Testing](https://docs.pytest.org/)

---

**Version**: 2.0.0  
**Last Updated**: 2025-11-09  
**Architecture**: Modular Enterprise
