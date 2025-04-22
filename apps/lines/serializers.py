from rest_framework import serializers
from apps.core.base.serializers import BaseModelSerializer, BaseGeoSerializer
from .models import Line, Stop, LineStop, LineBus, Favorite


class StopSerializer(BaseGeoSerializer):
    class Meta:
        model = Stop
        fields = [
            'id', 'name', 'code', 'address', 'image', 'description',
            'latitude', 'longitude', 'accuracy', 'metadata',
            'is_active', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class StopListSerializer(BaseGeoSerializer):
    class Meta:
        model = Stop
        fields = [
            'id', 'name', 'code', 'latitude', 'longitude'
        ]


class LineStopSerializer(BaseModelSerializer):
    stop_details = StopSerializer(source='stop', read_only=True)
    
    class Meta:
        model = LineStop
        fields = [
            'id', 'line', 'stop', 'order', 'distance_from_start',
            'estimated_time_from_start', 'is_active', 'created_at',
            'updated_at', 'stop_details'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'stop_details']


class LineStopCreateSerializer(BaseModelSerializer):
    class Meta:
        model = LineStop
        fields = [
            'line', 'stop', 'order', 'distance_from_start',
            'estimated_time_from_start'
        ]


class LineBusSerializer(BaseModelSerializer):
    bus_details = serializers.SerializerMethodField()
    
    class Meta:
        model = LineBus
        fields = [
            'id', 'line', 'bus', 'is_primary', 'is_active',
            'created_at', 'updated_at', 'bus_details'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'bus_details']
    
    def get_bus_details(self, obj):
        from apps.buses.serializers import BusSerializer
        return BusSerializer(obj.bus, context=self.context).data


class LineSerializer(BaseModelSerializer):
    start_location_details = StopSerializer(source='start_location', read_only=True)
    end_location_details = StopSerializer(source='end_location', read_only=True)
    stops_count = serializers.IntegerField(read_only=True)
    active_buses_count = serializers.IntegerField(read_only=True)
    
    class Meta:
        model = Line
        fields = [
            'id', 'name', 'description', 'color', 'start_location', 'end_location',
            'path', 'estimated_duration', 'distance', 'metadata', 'is_active',
            'created_at', 'updated_at', 'start_location_details', 'end_location_details',
            'stops_count', 'active_buses_count'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'start_location_details',
                           'end_location_details', 'stops_count', 'active_buses_count']


class LineDetailSerializer(LineSerializer):
    stops = serializers.SerializerMethodField()
    buses = serializers.SerializerMethodField()
    
    class Meta(LineSerializer.Meta):
        fields = LineSerializer.Meta.fields + ['stops', 'buses']
    
    def get_stops(self, obj):
        line_stops = obj.line_stops.filter(is_active=True).order_by('order')
        return LineStopSerializer(line_stops, many=True, context=self.context).data
    
    def get_buses(self, obj):
        line_buses = obj.line_buses.filter(is_active=True)
        return LineBusSerializer(line_buses, many=True, context=self.context).data


class LineCreateSerializer(BaseModelSerializer):
    stops = serializers.ListField(
        child=serializers.DictField(),
        required=False,
        write_only=True
    )
    
    class Meta:
        model = Line
        fields = [
            'name', 'description', 'color', 'start_location', 'end_location',
            'path', 'estimated_duration', 'distance', 'metadata', 'stops'
        ]
    
    def validate(self, attrs):
        start_location = attrs.get('start_location')
        end_location = attrs.get('end_location')
        stops = attrs.pop('stops', [])
        
        if start_location == end_location:
            raise serializers.ValidationError("Start and end locations cannot be the same")
        
        # Store for later use in create
        self.stops_data = stops
        
        return attrs
    
    def create(self, validated_data):
        stops_data = getattr(self, 'stops_data', [])
        
        line = Line.objects.create(**validated_data)
        
        # Create line stops
        if stops_data:
            for i, stop_data in enumerate(stops_data):
                stop_id = stop_data.get('id')
                if not stop_id:
                    continue
                
                try:
                    stop = Stop.objects.get(id=stop_id)
                except Stop.DoesNotExist:
                    continue
                
                LineStop.objects.create(
                    line=line,
                    stop=stop,
                    order=i,
                    distance_from_start=stop_data.get('distance_from_start', 0),
                    estimated_time_from_start=stop_data.get('estimated_time_from_start', 0)
                )
        
        # Always add start and end locations as stops if not already added
        if not LineStop.objects.filter(line=line, stop=line.start_location).exists():
            LineStop.objects.create(
                line=line,
                stop=line.start_location,
                order=0,
                distance_from_start=0,
                estimated_time_from_start=0
            )
        
        if not LineStop.objects.filter(line=line, stop=line.end_location).exists():
            last_order = LineStop.objects.filter(line=line).order_by('-order').first()
            last_order = last_order.order + 1 if last_order else 1
            
            LineStop.objects.create(
                line=line,
                stop=line.end_location,
                order=last_order,
                distance_from_start=line.distance,
                estimated_time_from_start=line.estimated_duration * 60  # Convert to seconds
            )
        
        return line


class FavoriteSerializer(BaseModelSerializer):
    line_details = LineSerializer(source='line', read_only=True)
    
    class Meta:
        model = Favorite
        fields = [
            'id', 'user', 'line', 'notification_threshold',
            'is_active', 'created_at', 'updated_at', 'line_details'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'line_details']


class LineBusCreateSerializer(BaseModelSerializer):
    class Meta:
        model = LineBus
        fields = ['line', 'bus', 'is_primary']


class LineStatusSerializer(serializers.Serializer):
    line_id = serializers.UUIDField()
    name = serializers.CharField()
    active_buses = serializers.IntegerField()
    buses = serializers.ListField(child=serializers.DictField())
    next_arrivals = serializers.ListField(child=serializers.DictField())
