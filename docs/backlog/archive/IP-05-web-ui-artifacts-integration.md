# IP-05 — Web UI Integration with Local Artifacts

**Status:** Planned  
**Priority:** High  
**Dependencies:** IP-01 (Completed)

## Objective

Integrate the React SPA Web UI with the local artifacts storage system to display generated materials from LearnFlow workflow. Add Web UI service to Docker Compose stack and ensure proper communication between services.

## Background

- LearnFlow service now saves artifacts to `data/artifacts/` directory structure
- Artifacts Service (FastAPI) exposes API for reading artifacts at port 8001
- Web UI exists but needs to be integrated into Docker Compose and configured to read from Artifacts Service
- Both services need to share the same volume mount for artifacts data

## Scope

### 1. Docker Integration
- Add Web UI service to docker-compose.yaml
- Configure proper networking between services
- Set up shared volume mounts for artifacts data
- Add health checks and restart policies

### 2. Environment Configuration
- Define environment variables for Web UI service
- Configure API endpoints (Artifacts Service URL)
- Set up CORS if needed for cross-origin requests
- Configure build-time and runtime variables

### 3. API Client Updates
- Update Web UI's ApiClient to connect to Artifacts Service
- Implement artifact fetching methods
- Handle thread/session navigation
- Add error handling for missing artifacts

### 4. Verify UI Components Compatibility
- Ensure existing components work with Artifacts Service API format
- Update API endpoints configuration
- Verify markdown rendering works with LaTeX formulas if needed

## Implementation Steps

### Step 1: Create Dockerfile for Web UI

Create `web-ui/Dockerfile`:
```dockerfile
FROM node:20-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 3001
CMD ["nginx", "-g", "daemon off;"]
```

### Step 2: Add Web UI to Docker Compose

Update `docker-compose.yaml`:
```yaml
web-ui:
  build:
    context: ./web-ui
    dockerfile: Dockerfile
  environment:
    - VITE_ARTIFACTS_API_URL=http://artifacts-service:8001
    - VITE_LEARNFLOW_API_URL=http://graph:8000
  ports:
    - "3001:3001"
  depends_on:
    artifacts-service:
      condition: service_healthy  # Wait for artifacts-service to be healthy
    graph:
      condition: service_started
  restart: always
  volumes:
    - ./data:/app/data:ro  # Read-only access to artifacts
  healthcheck:
    test: ["CMD", "wget", "--no-verbose", "--tries=1", "--spider", "http://localhost:3001/"]
    interval: 30s
    timeout: 10s
    start_period: 5s
    retries: 3
```

**Important:** The `condition: service_healthy` ensures that web-ui will only start after artifacts-service passes its health check. The artifacts-service already has a healthcheck configured in the current docker-compose.yaml, so this dependency prevents startup race conditions.

### Step 3: Configure Environment Variables

Update `web-ui/.env.example`:
```env
VITE_ARTIFACTS_API_URL=http://localhost:8001
VITE_LEARNFLOW_API_URL=http://localhost:8000
VITE_POLLING_INTERVAL=5000
VITE_MAX_RETRIES=3
```

### Step 4: Configure API Client Environment

Update `web-ui/src/services/ApiClient.ts` to use environment variable:
```typescript
// Update the baseURL in constructor to use environment variable
constructor(baseURL: string = import.meta.env.VITE_ARTIFACTS_API_URL || '/api') {
  this.baseURL = baseURL;
  // ... rest of the constructor
}
```

The existing ApiClient already has the necessary methods:
- `getThreads()` - list all threads
- `getThread(threadId)` - get thread metadata
- `getSessionFiles(threadId, sessionId)` - get session artifacts
- `getFileContent(threadId, sessionId, path)` - get specific file content

### Step 5: Create Nginx Configuration

Create `web-ui/nginx.conf`:
```nginx
server {
    listen 3001;
    server_name localhost;
    
    root /usr/share/nginx/html;
    index index.html;
    
    # Enable gzip
    gzip on;
    gzip_types text/plain application/javascript text/css application/json;
    
    # API proxy for artifacts service
    location /api/artifacts/ {
        proxy_pass http://artifacts-service:8001/;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
    }
    
    # SPA routing
    location / {
        try_files $uri $uri/ /index.html;
    }
}
```

## Validation Criteria

### Functional Requirements
- [ ] Web UI service runs in Docker Compose
- [ ] Can fetch and display thread metadata
- [ ] Can list and navigate sessions
- [ ] Renders markdown artifacts with proper formatting
- [ ] Shows LaTeX formulas if present
- [ ] Handles missing or incomplete artifacts gracefully

### Non-Functional Requirements
- [ ] Page load time < 2 seconds
- [ ] Smooth scrolling and navigation
- [ ] Responsive design for different screen sizes
- [ ] Proper error messages for failed requests
- [ ] Accessible UI following WCAG guidelines

## Configuration Checklist

### Environment Variables
- [ ] `VITE_ARTIFACTS_API_URL` - URL of Artifacts Service
- [ ] `VITE_LEARNFLOW_API_URL` - URL of LearnFlow API
- [ ] `VITE_POLLING_INTERVAL` - Refresh interval for updates
- [ ] `VITE_MAX_RETRIES` - Maximum retry attempts for failed requests

### Docker Configuration
- [ ] Web UI Dockerfile created
- [ ] Service added to docker-compose.yaml
- [ ] Proper network configuration
- [ ] Volume mounts configured
- [ ] Health checks implemented

### API Integration
- [ ] ApiClient updated with artifact methods
- [ ] CORS configured if needed
- [ ] Error handling implemented
- [ ] Loading states managed

## Potential Issues & Mitigations

### Issue 1: CORS Errors
**Mitigation:** Configure Artifacts Service to allow origins from Web UI domain, or use nginx proxy to avoid CORS

### Issue 2: Large Artifact Files
**Mitigation:** Implement pagination or lazy loading for large markdown files

### Issue 3: Real-time Updates
**Mitigation:** Start with polling, plan WebSocket implementation for FEAT-UI-104

### Issue 4: Volume Permissions
**Mitigation:** Ensure consistent UID/GID across containers or use read-only mounts where possible

## Dependencies

### External Services
- Artifacts Service must be running and accessible
- LearnFlow service must save artifacts in expected format
- Shared volume must be properly mounted

### Libraries
- React 18+
- react-markdown for content rendering
- Tailwind CSS for styling
- Vite for build tooling

## Success Metrics

- **Availability:** Web UI service uptime > 99%
- **Performance:** Artifact load time < 500ms for files under 1MB
- **User Experience:** Successful artifact display rate > 95%
- **Error Rate:** API error rate < 1%

## Next Steps

After successful implementation:
1. Add WebSocket support for real-time updates (FEAT-UI-104)
2. Implement artifact editing capabilities (FEAT-UI-105)
3. Add export functionality (PDF, DOCX)
4. Implement search within artifacts
5. Add user authentication and multi-tenancy support

## Notes

- Consider implementing a caching layer for frequently accessed artifacts
- Monitor disk usage as artifacts accumulate
- Plan for artifact lifecycle management (archival, deletion)
- Consider adding artifact versioning in future iterations