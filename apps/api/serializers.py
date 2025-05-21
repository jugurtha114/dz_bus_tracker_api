"""
Base serializers for DZ Bus Tracker API.
"""
from rest_framework import serializers


class BaseSerializer(serializers.ModelSerializer):
    """
    Base serializer with common functionality.
    """
    created_at = serializers.DateTimeField(read_only=True)
    updated_at = serializers.DateTimeField(read_only=True)

    def validate(self, attrs):
        """
        Common validation logic for all serializers.
        """
        # Get view and request
        view = self.context.get('view')
        request = self.context.get('request')

        # Call parent validation
        attrs = super().validate(attrs)

        return attrs


class ReadOnlyModelSerializer(BaseSerializer):
    """
    Serializer for read-only operations.
    """

    def __init__(self, *args, **kwargs):
        """
        Make all fields read-only.
        """
        super().__init__(*args, **kwargs)

        for field_name, field in self.fields.items():
            field.read_only = True


class NestedModelSerializer(BaseSerializer):
    """
    Serializer for nested model relationships.
    """

    def __init__(self, *args, **kwargs):
        """
        Initialize with an option to expand nested objects.
        """
        # Extract expand fields before calling parent constructor
        self.expand_fields = kwargs.pop('expand_fields', None)
        super().__init__(*args, **kwargs)

    def to_representation(self, instance):
        """
        Conditionally expand nested objects based on query params.
        """
        # Get the base representation
        representation = super().to_representation(instance)

        # Get the request and check for expand parameter
        request = self.context.get('request')
        if not request:
            return representation

        # Get the expand parameter - can be a comma-separated list
        expand = request.query_params.get('expand', '').split(',')

        # If no expand fields are requested or allowed, return as is
        if not expand or not self.expand_fields:
            return representation

        # Handle expansion of nested objects based on query params
        for field_name in expand:
            if field_name in self.expand_fields:
                # Get the serializer class from expand_fields dict
                serializer_class = self.expand_fields.get(field_name)

                # Get the related object
                related_obj = getattr(instance, field_name)

                # Skip if the object doesn't exist
                if related_obj is None:
                    continue

                # Check if it's a Manager (for reverse relations)
                if hasattr(related_obj, 'all'):
                    # Many objects, use a list serializer
                    serializer = serializer_class(
                        related_obj.all(),
                        many=True,
                        context=self.context
                    )
                else:
                    # Single object
                    serializer = serializer_class(
                        related_obj,
                        context=self.context
                    )

                # Replace the ID with the expanded object
                representation[field_name] = serializer.data

        return representation


class DynamicFieldsModelSerializer(BaseSerializer):
    """
    Serializer that takes an additional `fields` argument that controls
    which fields should be displayed.
    """

    def __init__(self, *args, **kwargs):
        """
        Initialize with an option to specify fields to include or exclude.
        """
        # Don't pass these kwargs to the superclass
        fields = kwargs.pop('fields', None)
        exclude = kwargs.pop('exclude', None)

        # Instantiate the superclass normally
        super().__init__(*args, **kwargs)

        if fields is not None:
            # Drop any fields that are not specified in the `fields` argument
            allowed = set(fields)
            existing = set(self.fields)
            for field_name in existing - allowed:
                self.fields.pop(field_name)

        if exclude is not None:
            # Drop specified fields
            for field_name in exclude:
                if field_name in self.fields:
                    self.fields.pop(field_name)


class FlexFieldsModelSerializer(BaseSerializer):
    """
    Serializer with dynamic field expansion based on request parameters.
    """
    expandable_fields = {}  # Override in subclasses

    def __init__(self, *args, **kwargs):
        """
        Initialize with options for field customization.
        """
        select_fields = kwargs.pop('fields', None)
        omit_fields = kwargs.pop('omit', None)
        expand_fields = kwargs.pop('expand', None)

        super().__init__(*args, **kwargs)

        # Handle field selection/omission
        if select_fields:
            allowed = set(select_fields)
            for field in list(self.fields.keys()):
                if field not in allowed:
                    self.fields.pop(field)

        if omit_fields:
            for field in omit_fields:
                if field in self.fields:
                    self.fields.pop(field)

        # Process expandable fields
        if not expand_fields:
            return

        for field in expand_fields:
            if field not in self.expandable_fields:
                continue

            # Get the related field info
            field_info = self.expandable_fields[field]

            # Basic validation - require at least a serializer class
            if not isinstance(field_info, dict) or 'serializer' not in field_info:
                continue

            # Extract serializer class and options
            serializer_class = field_info['serializer']
            serializer_kwargs = field_info.get('kwargs', {})
            source = field_info.get('source', field)

            # Set the expanded serializer in place of the original field
            self.fields[field] = serializer_class(
                source=source,
                read_only=True,
                many=field_info.get('many', False),
                context=self.context,
                **serializer_kwargs
            )


class TranslatedModelSerializer(BaseSerializer):
    """
    Serializer for models with translatable fields.
    """

    def to_representation(self, instance):
        """
        Convert instance to JSON according to the user's language.
        """
        representation = super().to_representation(instance)

        # Get request and language
        request = self.context.get('request')
        if not request:
            return representation

        language = getattr(request, 'LANGUAGE_CODE', 'fr')

        # Handle translated fields
        for field_name, field in self.fields.items():
            # Check if this is a translatable field
            if hasattr(instance, f"{field_name}_{language}"):
                # Get the translated value
                translated_value = getattr(instance, f"{field_name}_{language}")

                # Only update if there's a translation
                if translated_value:
                    representation[field_name] = translated_value

        return representation