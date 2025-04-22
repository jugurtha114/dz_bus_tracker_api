from rest_framework import serializers


class BaseModelSerializer(serializers.ModelSerializer):
    """
    Base serializer with common functionality.
    """
    created_at = serializers.DateTimeField(read_only=True)
    updated_at = serializers.DateTimeField(read_only=True)


class ReadWriteSerializerMixin:
    """
    Mixin for using different serializers for read and write operations.
    """
    read_serializer_class = None
    write_serializer_class = None

    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update']:
            return self.get_write_serializer_class()
        return self.get_read_serializer_class()
    
    def get_read_serializer_class(self):
        assert self.read_serializer_class is not None, (
            "'%s' should either include a `read_serializer_class` attribute, "
            "or override the `get_read_serializer_class()` method."
            % self.__class__.__name__
        )
        return self.read_serializer_class
    
    def get_write_serializer_class(self):
        assert self.write_serializer_class is not None, (
            "'%s' should either include a `write_serializer_class` attribute, "
            "or override the `get_write_serializer_class()` method."
            % self.__class__.__name__
        )
        return self.write_serializer_class


class DynamicFieldsModelSerializer(serializers.ModelSerializer):
    """
    A ModelSerializer that takes an additional `fields` argument that
    controls which fields should be displayed.
    """
    def __init__(self, *args, **kwargs):
        # Extract fields
        fields = kwargs.pop('fields', None)
        exclude_fields = kwargs.pop('exclude_fields', None)
        
        # Instantiate the superclass normally
        super().__init__(*args, **kwargs)
        
        if fields is not None:
            # Drop any fields that are not specified in the `fields` argument
            allowed = set(fields)
            existing = set(self.fields)
            for field_name in existing - allowed:
                self.fields.pop(field_name)
        
        if exclude_fields is not None:
            # Drop fields specified in the `exclude_fields` argument
            for field_name in exclude_fields:
                if field_name in self.fields:
                    self.fields.pop(field_name)


class RecursiveSerializer(serializers.Serializer):
    """
    Serializer for recursive relationships (used for nested tree structures).
    """
    def to_representation(self, instance):
        serializer = self.parent.parent.__class__(instance, context=self.context)
        return serializer.data


class BaseGeoSerializer(serializers.ModelSerializer):
    """
    Base serializer for models with geo point fields.
    """
    latitude = serializers.DecimalField(
        max_digits=9, 
        decimal_places=6,
        required=True
    )
    longitude = serializers.DecimalField(
        max_digits=9, 
        decimal_places=6,
        required=True
    )
    accuracy = serializers.FloatField(
        required=False, 
        allow_null=True
    )


class TimestampField(serializers.Field):
    """
    Field for handling Unix timestamps.
    """
    def to_representation(self, value):
        import calendar
        return calendar.timegm(value.timetuple())
    
    def to_internal_value(self, value):
        from datetime import datetime
        import pytz
        
        try:
            timestamp = float(value)
            return datetime.fromtimestamp(timestamp, tz=pytz.UTC)
        except (ValueError, TypeError):
            raise serializers.ValidationError("Invalid timestamp format")


class NestedCreateUpdateMixin:
    """
    Mixin for handling nested create and update operations.
    """
    def create(self, validated_data):
        nested_fields = self._get_nested_fields()
        
        # Extract nested data
        nested_data = {}
        for field in nested_fields:
            if field in validated_data:
                nested_data[field] = validated_data.pop(field)
        
        # Create the instance
        instance = super().create(validated_data)
        
        # Create nested instances
        self._handle_nested_data(instance, nested_data, create=True)
        
        return instance
    
    def update(self, instance, validated_data):
        nested_fields = self._get_nested_fields()
        
        # Extract nested data
        nested_data = {}
        for field in nested_fields:
            if field in validated_data:
                nested_data[field] = validated_data.pop(field)
        
        # Update the instance
        instance = super().update(instance, validated_data)
        
        # Update nested instances
        self._handle_nested_data(instance, nested_data, create=False)
        
        return instance
    
    def _get_nested_fields(self):
        """
        Get fields that should be handled as nested.
        """
        return getattr(self.Meta, 'nested_fields', [])
    
    def _handle_nested_data(self, instance, nested_data, create=False):
        """
        Handle nested data for create and update operations.
        """
        for field_name, data in nested_data.items():
            field = self.fields[field_name]
            
            if isinstance(data, list):
                # Many=True case
                self._handle_nested_many(instance, field_name, field, data, create)
            else:
                # Single instance case
                self._handle_nested_single(instance, field_name, field, data, create)
    
    def _handle_nested_many(self, instance, field_name, field, data, create):
        """
        Handle nested data with many=True case.
        """
        if not data:
            return
            
        # Get related model
        model = field.child.Meta.model
        
        # Get FK name to parent
        fk_name = None
        for name, field_type in model._meta.fields_map.items():
            if field_type.related_model == instance.__class__:
                fk_name = name
                break
        
        if not fk_name:
            return
            
        # If updating, delete existing related instances
        if not create:
            model.objects.filter(**{fk_name: instance}).delete()
        
        # Create new related instances
        for item in data:
            item[fk_name] = instance
            serializer = field.child.__class__(data=item, context=self.context)
            serializer.is_valid(raise_exception=True)
            serializer.save()
    
    def _handle_nested_single(self, instance, field_name, field, data, create):
        """
        Handle nested data with single object case.
        """
        if not data:
            return
            
        # Get related model and instance if exists
        model = field.Meta.model
        
        # Try to get related field name
        fk_name = None
        reverse_name = None
        
        # Check if the field is a direct FK from instance
        for name, field_type in instance.__class__._meta.fields_map.items():
            if name == field_name:
                fk_name = name
                break
        
        # If not a direct FK, check for reverse relation
        if not fk_name:
            for name, field_type in model._meta.fields_map.items():
                if field_type.related_model == instance.__class__:
                    reverse_name = name
                    break
        
        # Update or create the related instance
        if fk_name:
            # Direct FK from instance
            serializer = field.__class__(data=data, context=self.context)
            serializer.is_valid(raise_exception=True)
            related_instance = serializer.save()
            
            # Set FK on parent
            setattr(instance, fk_name, related_instance)
            instance.save(update_fields=[fk_name])
        elif reverse_name:
            # Reverse FK from related model
            data[reverse_name] = instance
            serializer = field.__class__(data=data, context=self.context)
            serializer.is_valid(raise_exception=True)
            serializer.save()
