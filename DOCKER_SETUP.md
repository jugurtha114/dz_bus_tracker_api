# Docker Setup Guide for DZ Bus Tracker

This guide explains how to set up and run the DZ Bus Tracker application using Docker for both local development and production environments.

## Quick Start

### Local Development

1. **Clone the repository and navigate to the project directory**
   ```bash
   cd /path/to/dz_bus_tracker_v2
   ```

2. **Copy the environment file**
   ```bash
   cp .env.local .env
   ```

3. **Start the services**
   ```bash
   # Start database services first
   docker compose up -d postgres redis
   
   # Wait for services to be healthy, then start the application
   docker compose up -d
   ```

4. **Test the setup**
   ```bash
   python test_docker_setup.py
   ```

5. **Access the application**
   - API: http://localhost:8000/api/
   - Admin: http://localhost:8000/admin/
   - Health Check: http://localhost:8000/health/
   - Flower (Celery Monitoring): http://localhost:5555/

### Production Deployment

1. **Copy and configure production environment**
   ```bash
   cp .env.example .env
   # Edit .env with your production values
   ```

2. **Deploy with production compose**
   ```bash
   docker compose -f docker-compose.prod.yml up -d
   ```

## Architecture

### Services

- **postgres**: PostgreSQL 15 database
- **redis**: Redis 7 for caching and Celery broker
- **web**: Django application server
- **celery**: Background task worker
- **celery-beat**: Task scheduler
- **flower**: Celery monitoring (development only)
- **nginx**: Reverse proxy and static file server (production only)

### Ports

#### Local Development
- **5433**: PostgreSQL (mapped from 5432 to avoid conflicts)
- **6380**: Redis (mapped from 6379 to avoid conflicts)
- **8000**: Django application
- **5555**: Flower monitoring

#### Production
- **80**: HTTP (nginx)
- **443**: HTTPS (nginx, when SSL configured)

## Configuration

### Environment Variables

Create a `.env` file from `.env.example` and configure the following:

#### Required for Production
```bash
SECRET_KEY=your-super-secret-key
ALLOWED_HOSTS=yourdomain.com,www.yourdomain.com
DB_PASSWORD=secure-database-password
REDIS_PASSWORD=secure-redis-password
```

#### Email Configuration
```bash
EMAIL_HOST=smtp.gmail.com
EMAIL_HOST_USER=your-email@gmail.com
EMAIL_HOST_PASSWORD=your-app-password
```

#### External Services
```bash
FIREBASE_SERVER_KEY=your-firebase-key
TWILIO_ACCOUNT_SID=your-twilio-sid
TWILIO_AUTH_TOKEN=your-twilio-token
GOOGLE_MAPS_API_KEY=your-maps-key
```

### Database Initialization

The application will automatically:
- Run database migrations
- Create a superuser (admin@dzbustracker.com / admin123) for development
- Load sample data (development only)

## File Structure

```
├── Dockerfile                 # Multi-stage Docker build
├── docker-compose.yml         # Local development setup
├── docker-compose.prod.yml    # Production setup
├── .dockerignore              # Files to exclude from build
├── .env.example               # Environment template
├── .env.local                 # Local development env
├── scripts/
│   ├── entrypoint.sh         # Application startup script
│   └── health_check.sh       # Health check script
├── nginx/
│   ├── nginx.conf            # Main nginx configuration
│   └── conf.d/
│       └── dz_bus_tracker.conf  # App-specific nginx config
└── test_docker_setup.py      # Setup verification script
```

## Commands

### Development Commands
```bash
# Start all services
docker compose up -d

# View logs
docker compose logs -f [service_name]

# Run Django commands
docker compose exec web python manage.py [command]

# Run tests
docker compose exec web python manage.py test

# Access Django shell
docker compose exec web python manage.py shell

# Stop all services
docker compose down

# Rebuild images
docker compose build --no-cache
```

### Production Commands
```bash
# Deploy
docker compose -f docker-compose.prod.yml up -d

# Scale workers
docker compose -f docker-compose.prod.yml up -d --scale celery=3

# Update application
docker compose -f docker-compose.prod.yml pull
docker compose -f docker-compose.prod.yml up -d

# Backup database
docker compose -f docker-compose.prod.yml exec postgres pg_dump -U $DB_USER $DB_NAME > backup.sql
```

## Troubleshooting

### Common Issues

1. **Port Conflicts**
   - PostgreSQL: Change port 5433 in docker-compose.yml
   - Redis: Change port 6380 in docker-compose.yml

2. **Permission Errors**
   ```bash
   sudo chown -R $USER:$USER media/ static/ logs/
   ```

3. **Database Connection Issues**
   ```bash
   # Check if PostgreSQL is running
   docker compose logs postgres
   
   # Verify health
   docker compose ps
   ```

4. **Build Failures**
   ```bash
   # Clean build
   docker compose down
   docker system prune -f
   docker compose build --no-cache
   ```

### Health Checks

All services include health checks:
- **postgres**: `pg_isready`
- **redis**: `redis-cli ping`
- **web**: HTTP request to `/health/`
- **celery**: `celery inspect ping`

### Monitoring

- **Application logs**: `docker compose logs -f web`
- **Database logs**: `docker compose logs -f postgres`
- **Celery tasks**: http://localhost:5555 (development)
- **System resources**: `docker stats`

## Security Notes

### Development
- Uses default passwords for convenience
- Debug mode enabled
- All ports exposed to localhost

### Production
- Change all default passwords
- Use environment variables for secrets
- Enable HTTPS with SSL certificates
- Restrict network access with firewalls
- Regular security updates

## Performance Optimization

### Production Tuning
- Adjust worker counts based on CPU cores
- Configure PostgreSQL shared_buffers and work_mem
- Use Redis persistence settings
- Enable gzip compression in nginx
- Configure static file caching

### Scaling
- Use docker-compose scale for horizontal scaling
- Consider using external managed databases
- Implement load balancing with multiple nginx instances
- Use CDN for static files

## Backup and Recovery

### Database Backup
```bash
# Create backup
docker compose exec postgres pg_dump -U postgres dz_bus_tracker_db > backup.sql

# Restore backup
docker compose exec -T postgres psql -U postgres dz_bus_tracker_db < backup.sql
```

### Media Files Backup
```bash
# Backup media files
docker run --rm -v dz_bus_tracker_v2_media_files:/data -v $(pwd):/backup alpine tar czf /backup/media_backup.tar.gz -C /data .

# Restore media files
docker run --rm -v dz_bus_tracker_v2_media_files:/data -v $(pwd):/backup alpine tar xzf /backup/media_backup.tar.gz -C /data
```