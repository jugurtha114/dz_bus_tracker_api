# DZ Bus Tracker - Backend API

A modular, scalable, and network-optimized backend API using Django REST Framework for DZ Bus Tracker, a real-time public bus tracking application tailored for Algeria.

## 🔑 Key Features

- **Low bandwidth optimization** supporting 2G networks
- **Real-time GPS tracking** with high precision location data
- **Role-based access** for admins, drivers, and passengers
- **Secure driver and bus registration** with admin verification
- **Comprehensive ETA calculation** for bus arrivals
- **Multilingual support** (Arabic, French, and English)
- **Scalable architecture** with Redis caching and Celery background tasks
- **Offline mode support** with batch data synchronization

## 🛠️ Technology Stack

- **Backend**: Django 5.2 + Django REST Framework
- **Database**: PostgreSQL with PostGIS extension
- **Cache & Queue**: Redis + Celery
- **Serialization**: ORMSGPack for optimal network performance
- **Containerization**: Docker + Docker Compose
- **Web Server**: Nginx (production)
- **Maps**: Google Maps API integration

## 📋 Requirements

- Python 3.10+
- PostgreSQL 14+ with PostGIS
- Redis 7+
- Docker and Docker Compose (for containerized deployment)

## 🚀 Quick Start

### Using Docker (Recommended)

1. Clone the repository:
   ```bash
   git clone https://github.com/dzbustracker/dz-bus-tracker.git
   cd dz-bus-tracker
   ```

2. Copy the environment files:
   ```bash
   cp .env.sample .env
   ```

3. Build and start the containers:
   ```bash
   docker-compose up -d
   ```

4. Access the API at http://localhost:8000/api/v1/

For detailed Docker instructions, see [Docker Setup](docker-README.md).

### Manual Setup

1. Create a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements/local.txt
   ```

3. Configure environment variables:
   ```bash
   cp .env.sample .env
   # Edit .env with your settings
   ```

4. Run migrations:
   ```bash
   python manage.py migrate
   ```

5. Create a superuser:
   ```bash
   python manage.py createsuperuser
   ```

6. Run the development server:
   ```bash
   python manage.py runserver
   ```

## 📚 API Documentation

API documentation is available at these endpoints when the server is running:

- Swagger UI: `/api/v1/schema/swagger/`
- ReDoc: `/api/v1/schema/redoc/`
- OpenAPI Schema: `/api/v1/schema/`

## 🔒 Authentication

The API uses JWT-based authentication. To obtain tokens:

```http
POST /api/v1/login/
{
    "email": "user@example.com",
    "password": "password"
}
```

Response:

```json
{
    "access": "eyJ0eXAiOi...",
    "refresh": "eyJ0eXAiOi...",
    "user": {
        "id": "uuid",
        "email": "user@example.com",
        "user_type": "driver",
        ...
    }
}
```

Use the access token in the Authorization header:

```
Authorization: Bearer eyJ0eXAiOi...
```

## 🧪 Testing

Run the test suite:

```bash
python manage.py test
```

With coverage:

```bash
coverage run --source='.' manage.py test
coverage report
```

## 🌐 Internationalization

The API supports three languages:

- French (default)
- Arabic
- English

Set the language preference in the `Accept-Language` header:

```
Accept-Language: ar
```

## 🚌 Core Modules

- **Authentication**: User management with role-based permissions
- **Drivers**: Driver registration, verification, and rating
- **Buses**: Bus registration, verification, and assignment to lines
- **Lines**: Line and stop management with scheduling
- **Tracking**: Real-time GPS tracking with offline support
- **ETA**: Estimated time of arrival calculation and notification
- **Analytics**: Trip statistics, delay reporting, and usage metrics
- **Feedback**: User feedback and issue reporting system

## 🤝 Contributing

Contributions are welcome! Please check out our [contributing guide](CONTRIBUTING.md).

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 📧 Contact

For questions or support, contact us at info@dzbustracker.com.
# dz_bus_tracker_api
