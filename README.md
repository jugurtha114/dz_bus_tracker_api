# DZ Bus Tracker 🚌

Real-time bus tracking application for Algeria

## 🚀 Project Overview

**DZ Bus Tracker** is a mobile application designed to modernize and simplify public bus transportation in Algeria. It connects **bus drivers** and **passengers** in real time, allowing everyone to enjoy smoother, safer, and more reliable commutes.

## 🛠️ Technology Stack

- **Backend**: Django 5.2, Django REST Framework
- **Database**: PostgreSQL
- **Cache**: Redis
- **Task Queue**: Celery
- **Authentication**: JWT
- **Internationalization**: Support for French (default), Arabic, and English
- **Push Notifications**: Firebase Cloud Messaging
- **SMS Notifications**: Twilio
- **Geolocation**: Google Maps API

## ✨ Features

### For Passengers 👥

- Live GPS location of buses on a line
- Estimated arrival times for buses
- Information about drivers, including ratings
- Real-time passenger load information
- Estimated seat availability at stops
- Driver rating system

### For Drivers 👨‍✈️

- Start and stop tracking
- View waiting passengers at each stop
- Monitor available seats
- Receive ratings and feedback
- Earn badges and achievements for safe and punctual service

### For Admins 👨‍💼

- Manage drivers, buses, lines, and schedules
- Approve driver registrations
- View system analytics and reports
- Monitor anomalies and service issues

## 🧩 Project Structure

The project follows a modular Django structure with the following apps:

- **accounts**: User and profile management
- **buses**: Bus and bus location management
- **drivers**: Driver registration, approval, and rating
- **lines**: Bus lines, stops, and schedules
- **tracking**: Real-time tracking, trips, and passenger counts
- **notifications**: Push notifications, SMS, and email alerts
- **api**: API endpoints and versioning
- **core**: Shared utilities and base classes

## 📋 Getting Started

### Prerequisites

- Python 3.12+
- PostgreSQL
- Redis
- A virtual environment tool

### Installation

1. Clone the repository
```bash
git clone https://github.com/your-username/dz_bus_tracker.git
cd dz_bus_tracker