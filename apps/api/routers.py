"""
Router configuration for DZ Bus Tracker API.
"""
from django.urls import include, path
from rest_framework.routers import DefaultRouter, SimpleRouter


class NestedDefaultRouter(DefaultRouter):
    """
    Router that allows nested resources.
    """

    def __init__(self, *args, **kwargs):
        """
        Initialize with parent router and parent prefix.
        """
        self.parent_router = kwargs.pop('parent_router', None)
        self.parent_prefix = kwargs.pop('parent_prefix', None)
        super().__init__(*args, **kwargs)

        # If initialized with a parent, register with parent
        if self.parent_router and self.parent_prefix:
            self.parent_router.register_nested_router(self.parent_prefix, self)

    def register_nested_router(self, prefix, router):
        """
        Register a nested router with this router.
        """
        self.registry.append((prefix, router, None))

    def get_urls(self):
        """
        Generate URLs for this router, including nested routes.
        """
        urls = super().get_urls()

        # Add nested router URLs
        for prefix, router, _ in self.registry:
            if isinstance(router, NestedDefaultRouter):
                nested_urls = router.get_urls()

                # Add the parent prefix to the nested URLs
                if self.parent_prefix:
                    prefix = f"{self.parent_prefix}/{prefix}"

                urls.append(path(f"{prefix}/", include(nested_urls)))

        return urls


class VersionedRouter:
    """
    Router for versioned APIs.
    """

    def __init__(self, base_name=None):
        """
        Initialize with a base name.
        """
        self.base_name = base_name or 'api'
        self.routers = {}

    def get_router(self, version='v1'):
        """
        Get or create a router for a specific version.
        """
        if version not in self.routers:
            self.routers[version] = DefaultRouter()

        return self.routers[version]

    def get_urls(self):
        """
        Generate URLs for all versions.
        """
        urls = []

        for version, router in self.routers.items():
            urls.append(path(f"{version}/", include(router.urls)))

        return urls


# Create main API router
api_router = VersionedRouter()

# Get v1 router
v1_router = api_router.get_router('v1')