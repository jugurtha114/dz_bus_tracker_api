from setuptools import setup, find_packages

setup(
    name="dz_bus_tracker",
    version="1.0.0",
    packages=find_packages(),
    include_package_data=True,
    install_requires=[
        'Django>=5.1.8',
        'djangorestframework>=3.16.0',
        'django-environ>=0.11.2',
        'django-cors-headers>=4.3.1',
        'django-filter>=24.1',
        "djangorestframework-simplejwt==5.4.0",
        'psycopg>=3.1.18',
        'redis>=5.0.2',
        'celery>=5.3.6',
        'orjson>=3.10.0',
        'ormsgpack>=1.3.0',
        'django-redis>=5.4.0',
        'geopy>=2.4.1',
    ],
    python_requires='>=3.11',
    author="DZ Bus Tracker Team",
    author_email="info@dzbustracker.com",
    description="A scalable DRF backend for bus tracking in Algeria",
    keywords="bus, tracking, gps, drf, django",
    url="https://github.com/dzbustracker/dz-bus-tracker",
    project_urls={
        "Documentation": "https://github.com/dzbustracker/dz-bus-tracker/docs",
        "Source Code": "https://github.com/dzbustracker/dz-bus-tracker",
    },
    classifiers=[
        'Development Status :: 4 - Beta',
        'Environment :: Web Environment',
        'Framework :: Django',
        'Framework :: Django :: 5.1.8',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.11',
        'Programming Language :: Python :: 3.12',
        'Programming Language :: Python :: 3.13',
        'Topic :: Internet :: WWW/HTTP',
        'Topic :: Internet :: WWW/HTTP :: Dynamic Content',
    ],
)
