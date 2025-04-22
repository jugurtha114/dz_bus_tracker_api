# DZ Bus Tracker - Docker Setup

This document explains how to deploy the DZ Bus Tracker backend using Docker and Docker Compose.

## Prerequisites

- Docker Engine (20.10.0+)
- Docker Compose v2 (2.0.0+)
- Make the entrypoint script executable: `chmod +x docker-entrypoint.sh`

## Development Environment

### Setup

1. Copy the sample environment file:
   ```bash
   cp .env.sample .env
   ```

2. Customize the `.env` file with your settings.

3. Build and start the development environment:
   ```bash
   docker-compose build
   docker-compose up
   ```

4. Access the application at http://localhost:8000

### Development Commands

- Run the application:
  ```bash
  docker-compose up
  ```

- Run in detached mode:
  ```bash
  docker-compose up -d
  ```

- Stop containers:
  ```bash
  docker-compose down
  ```

- Access a shell in the web container:
  ```bash
  docker-compose exec web bash
  ```

- Run Django management commands:
  ```bash
  docker-compose exec web python manage.py [command]
  ```

- Run tests:
  ```bash
  docker-compose exec web python manage.py test
  ```

- View logs:
  ```bash
  docker-compose logs -f
  ```

- Restart a specific service:
  ```bash
  docker-compose restart [service]
  ```

## Production Environment

### Setup

1. Copy the sample environment file for production:
   ```bash
   cp .env.sample .env.prod
   ```

2. Customize the `.env.prod` file with your production settings:
   - Set `DEBUG=False`
   - Configure secure passwords and keys
   - Set proper domain name and allowed hosts
   - Configure email, Firebase, and Twilio settings

3. Create required directories:
   ```bash
   mkdir -p nginx/certbot/conf nginx/certbot/www
   ```

4. Configure SSL with certbot (before starting services):
   ```bash
   docker-compose run --rm certbot certonly --webroot --webroot-path=/var/www/certbot -d yourdomain.com -d www.yourdomain.com
   ```

5. Build and start the production environment:
   ```bash
   docker-compose -f docker-compose.prod.yml build
   docker-compose -f docker-compose.prod.yml up -d
   ```

6. Access the application at https://yourdomain.com

### Production Commands

- Start production services:
  ```bash
  docker-compose -f docker-compose.prod.yml up -d
  ```

- Stop production services:
  ```bash
  docker-compose -f docker-compose.prod.yml down
  ```

- View production logs:
  ```bash
  docker-compose -f docker-compose.prod.yml logs -f
  ```

- Execute commands in production:
  ```bash
  docker-compose -f docker-compose.prod.yml exec web python manage.py [command]
  ```

- Restart a specific service:
  ```bash
  docker-compose -f docker-compose.prod.yml restart [service]
  ```

- Scale web workers in production:
  ```bash
  docker-compose -f docker-compose.prod.yml up -d --scale web=3
  ```

## Docker Configuration Details

### Services

The Docker Compose configuration includes the following services:

#### Development Environment
- **web**: Django application server
- **db**: PostgreSQL database with PostGIS extension
- **redis**: Redis server for caching and Celery broker
- **celery**: Celery worker for background tasks
- **celery-beat**: Celery beat for scheduled tasks
- **flower**: Celery monitoring interface

#### Production Environment
- All services from development, plus:
- **nginx**: Web server/reverse proxy with SSL termination
- **certbot**: For automatic SSL certificate generation and renewal

### Volumes

- **postgres_data**: Persistent PostgreSQL data
- **redis_data**: Persistent Redis data
- **static_volume**: Django static files
- **media_volume**: User-uploaded media files

### Networks

- **dz_bus_network**: Shared network for all services

## Best Practices

1. **Environment Variables**:
   - Never commit `.env` or `.env.prod` files to version control
   - Use different credentials for development and production

2. **Security**:
   - Run services as non-root users where possible
   - Use environment variables for sensitive data
   - Keep Docker and all services updated
   - Configure proper SSL in production

3. **Backups**:
   - Regularly backup PostgreSQL data
   - Use a script like:
     ```bash
     docker-compose -f docker-compose.prod.yml exec db pg_dump -U postgres dz_bus_tracker > backup_$(date +%Y-%m-%d).sql
     ```

4. **Monitoring**:
   - Use Flower to monitor Celery tasks at http://localhost:5555
   - Consider adding Prometheus and Grafana for comprehensive monitoring

5. **Scaling**:
   - Web and Celery services can be scaled horizontally
   - For heavy loads, consider using Docker Swarm or Kubernetes

## Troubleshooting

### Common Issues

1. **Database connection errors**:
   - Ensure PostgreSQL is running: `docker-compose ps`
   - Check database settings in `.env` file
   - Verify network connectivity between containers

2. **Permission errors**:
   - Ensure proper permissions on mounted volumes
   - Check if services are running as the correct user

3. **Nginx/SSL issues**:
   - Verify SSL certificates are properly generated
   - Check Nginx logs: `docker-compose -f docker-compose.prod.yml logs nginx`
   - Ensure domain name is correctly configured in Nginx

4. **Container startup failures**:
   - Check service logs: `docker-compose logs [service]`
   - Ensure required environment variables are set
   - Verify entrypoint script permissions: `chmod +x docker-entrypoint.sh`

### Viewing Logs

```bash
# View logs for all services
docker-compose logs

# Follow logs in real-time
docker-compose logs -f

# View logs for a specific service
docker-compose logs [service]

# View logs with timestamps
docker-compose logs -f --timestamps
```

## Deployment Strategy

For deployment updates, a zero-downtime approach is recommended:

1. Build new images:
   ```bash
   docker-compose -f docker-compose.prod.yml build
   ```

2. Apply database migrations:
   ```bash
   docker-compose -f docker-compose.prod.yml run --rm web python manage.py migrate
   ```

3. Restart services one by one:
   ```bash
   docker-compose -f docker-compose.prod.yml up -d --no-deps --build web
   docker-compose -f docker-compose.prod.yml restart celery
   docker-compose -f docker-compose.prod.yml restart celery-beat
   ```

This approach ensures your application remains available during updates.

## Performance Tuning

- Adjust PostgreSQL configuration for better performance
- Configure appropriate Gunicorn worker count (usually 2-4× CPU cores)
- Tune Redis cache settings
- Use connection pooling for databases
- Implement proper caching strategies in the application

## Further Resources

- [Docker Documentation](https://docs.docker.com/)
- [Docker Compose Documentation](https://docs.docker.com/compose/)
- [Nginx Documentation](https://nginx.org/en/docs/)
- [PostgreSQL Documentation](https://www.postgresql.org/docs/)
- [Django Deployment Checklist](https://docs.djangoproject.com/en/stable/howto/deployment/checklist/)