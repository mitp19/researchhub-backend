"""
Serializers for reputation breakdown and history API endpoints.

PR #4: Frontend API - Reputation Breakdown Endpoints
"""

from rest_framework import serializers


class RecentReputationChangeSerializer(serializers.Serializer):
    """Serializer for individual reputation changes in recent history."""
    
    contribution_type = serializers.CharField()
    contribution_type_display = serializers.CharField()
    rsc_amount = serializers.DecimalField(max_digits=19, decimal_places=8)
    reputation_earned = serializers.IntegerField()
    date = serializers.DateTimeField()
    content_type = serializers.CharField()
    content_id = serializers.IntegerField()
    is_deleted = serializers.BooleanField()


class RSCSummarySerializer(serializers.Serializer):
    """Serializer for RSC summary data."""
    
    total_rsc_received = serializers.DecimalField(max_digits=19, decimal_places=8)
    tips_received = serializers.DecimalField(max_digits=19, decimal_places=8)
    bounties_received = serializers.DecimalField(max_digits=19, decimal_places=8)
    proposals_funded = serializers.DecimalField(max_digits=19, decimal_places=8)
    proposals_funded_given = serializers.DecimalField(max_digits=19, decimal_places=8)


class ReputationBreakdownSerializer(serializers.Serializer):
    """Serializer for complete reputation breakdown."""
    
    total_reputation = serializers.IntegerField()
    breakdown_by_type = serializers.DictField()
    rsc_summary = RSCSummarySerializer()
    recent_changes = RecentReputationChangeSerializer(many=True)


class ReputationHistoryPointSerializer(serializers.Serializer):
    """Serializer for a single point in reputation history."""
    
    date = serializers.DateField()
    reputation = serializers.IntegerField()


class ReputationHistorySerializer(serializers.Serializer):
    """Serializer for reputation history over time."""
    
    history = ReputationHistoryPointSerializer(many=True)
    change_over_period = serializers.IntegerField()
    percent_change = serializers.FloatField()
    start_reputation = serializers.IntegerField()
    end_reputation = serializers.IntegerField()


class ReputationStatsSerializer(serializers.Serializer):
    """Serializer for user reputation statistics."""
    
    user_reputation = serializers.IntegerField()
    percentile = serializers.FloatField()
    rank = serializers.IntegerField()
    total_users = serializers.IntegerField()
    avg_reputation = serializers.FloatField()
    top_contribution_type = serializers.CharField()
    top_contribution_rep = serializers.IntegerField()

