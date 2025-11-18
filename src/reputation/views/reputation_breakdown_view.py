"""
API views for reputation breakdown and analytics.

PR #4: Frontend API - Reputation Breakdown Endpoints
"""

from datetime import datetime, timedelta
from decimal import Decimal

from django.db.models import Sum, Count, Q, Max
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from reputation.models import Score, ScoreChange
from reputation.related_models.contribution_weight import ContributionWeight
from reputation.serializers.reputation_breakdown_serializer import (
    ReputationBreakdownSerializer,
    ReputationHistorySerializer,
    ReputationStatsSerializer,
)
from user.models import Author, User


class ReputationBreakdownView(APIView):
    """
    Get detailed breakdown of user's reputation by source.
    
    Shows how reputation was earned across different contribution types,
    RSC flows, and includes recent reputation changes.
    
    GET /api/reputation/breakdown/?user_id=123
    """
    
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        user_id = request.query_params.get('user_id')
        
        if not user_id:
            return Response(
                {'error': 'user_id parameter is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            author = Author.objects.get(user_id=user_id)
        except Author.DoesNotExist:
            return Response(
                {'error': 'Author not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Get all score changes for this author
        score_changes = ScoreChange.objects.filter(
            score__author=author
        ).select_related(
            'changed_content_type',
            'score__hub'
        )
        
        # Aggregate by contribution type
        breakdown = score_changes.values('contribution_type').annotate(
            total_rep=Sum('score_change'),
            count=Count('id')
        ).order_by('-total_rep')
        
        breakdown_by_type = {
            item['contribution_type']: item['total_rep'] 
            for item in breakdown
        }
        
        # Calculate RSC summary
        rsc_summary = self._calculate_rsc_summary(score_changes)
        
        # Get recent changes (last 20)
        recent_changes = self._get_recent_changes(score_changes)
        
        # Calculate total reputation
        total_reputation = sum(breakdown_by_type.values())
        
        data = {
            'total_reputation': total_reputation,
            'breakdown_by_type': breakdown_by_type,
            'rsc_summary': rsc_summary,
            'recent_changes': recent_changes,
        }
        
        serializer = ReputationBreakdownSerializer(data)
        return Response(serializer.data)
    
    def _calculate_rsc_summary(self, score_changes):
        """Calculate summary of RSC received."""
        tips = score_changes.filter(
            contribution_type='TIP_RECEIVED'
        ).aggregate(total=Sum('rsc_amount'))['total'] or Decimal('0')
        
        bounties = score_changes.filter(
            contribution_type='BOUNTY_PAYOUT'
        ).aggregate(total=Sum('rsc_amount'))['total'] or Decimal('0')
        
        proposals_funded = score_changes.filter(
            contribution_type='PROPOSAL_FUNDED'
        ).aggregate(total=Sum('rsc_amount'))['total'] or Decimal('0')
        
        proposals_given = score_changes.filter(
            contribution_type='PROPOSAL_FUNDING_CONTRIBUTION'
        ).aggregate(total=Sum('rsc_amount'))['total'] or Decimal('0')
        
        total = tips + bounties + proposals_funded + proposals_given
        
        return {
            'total_rsc_received': total,
            'tips_received': tips,
            'bounties_received': bounties,
            'proposals_funded': proposals_funded,
            'proposals_funded_given': proposals_given,
        }
    
    def _get_recent_changes(self, score_changes):
        """Get recent reputation changes."""
        recent = score_changes.order_by('-created_date')[:20]
        
        changes = []
        for sc in recent:
            changes.append({
                'contribution_type': sc.contribution_type,
                'contribution_type_display': ContributionWeight.get_contribution_type_display(
                    sc.contribution_type
                ),
                'rsc_amount': sc.rsc_amount,
                'reputation_earned': sc.score_change,
                'date': sc.created_date,
                'content_type': sc.changed_content_type.model if sc.changed_content_type else None,
                'content_id': sc.changed_object_id,
                'is_deleted': sc.is_deleted,
            })
        
        return changes


class ReputationHistoryView(APIView):
    """
    Get reputation history over time.
    
    Shows how reputation changed over a specified period.
    
    GET /api/reputation/history/?user_id=123&days=30
    """
    
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        user_id = request.query_params.get('user_id')
        days = int(request.query_params.get('days', 30))
        
        if not user_id:
            return Response(
                {'error': 'user_id parameter is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            author = Author.objects.get(user_id=user_id)
        except Author.DoesNotExist:
            return Response(
                {'error': 'Author not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Get date range
        end_date = timezone.now()
        start_date = end_date - timedelta(days=days)
        
        # Get all score changes in this period
        score_changes = ScoreChange.objects.filter(
            score__author=author,
            created_date__gte=start_date,
            created_date__lte=end_date
        ).order_by('created_date')
        
        if not score_changes.exists():
            return Response({
                'history': [],
                'change_over_period': 0,
                'percent_change': 0.0,
                'start_reputation': 0,
                'end_reputation': 0,
            })
        
        # Build history by aggregating score_after_change by day
        history = []
        current_date = start_date.date()
        
        # Get starting reputation (last score before period)
        start_score_change = ScoreChange.objects.filter(
            score__author=author,
            created_date__lt=start_date
        ).order_by('-created_date').first()
        
        start_reputation = start_score_change.score_after_change if start_score_change else 0
        
        while current_date <= end_date.date():
            # Get last score change for this day
            day_end = timezone.make_aware(
                datetime.combine(current_date, datetime.max.time())
            )
            
            last_sc_of_day = score_changes.filter(
                created_date__lte=day_end
            ).order_by('-created_date').first()
            
            reputation = last_sc_of_day.score_after_change if last_sc_of_day else start_reputation
            
            history.append({
                'date': current_date,
                'reputation': reputation
            })
            
            current_date += timedelta(days=1)
        
        # Calculate change
        end_reputation = history[-1]['reputation'] if history else start_reputation
        change_over_period = end_reputation - start_reputation
        percent_change = (
            (change_over_period / start_reputation * 100) 
            if start_reputation > 0 
            else 0.0
        )
        
        data = {
            'history': history,
            'change_over_period': change_over_period,
            'percent_change': percent_change,
            'start_reputation': start_reputation,
            'end_reputation': end_reputation,
        }
        
        serializer = ReputationHistorySerializer(data)
        return Response(serializer.data)


class ReputationStatsView(APIView):
    """
    Get user reputation statistics and comparison to community.
    
    Shows percentile, rank, and top contribution types.
    
    GET /api/reputation/stats/?user_id=123
    """
    
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        user_id = request.query_params.get('user_id')
        
        if not user_id:
            return Response(
                {'error': 'user_id parameter is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            user = User.objects.get(id=user_id)
            author = user.author_profile
        except (User.DoesNotExist, Author.DoesNotExist):
            return Response(
                {'error': 'User not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Get user's total reputation across all hubs
        user_scores = Score.objects.filter(author=author)
        user_reputation = sum(s.score for s in user_scores)
        
        # Calculate rank and percentile
        total_users_with_rep = User.objects.filter(reputation__gt=0).count()
        users_with_higher_rep = User.objects.filter(reputation__gt=user.reputation).count()
        rank = users_with_higher_rep + 1
        
        percentile = (
            ((total_users_with_rep - rank) / total_users_with_rep * 100)
            if total_users_with_rep > 0
            else 0.0
        )
        
        # Calculate average reputation
        avg_reputation = User.objects.filter(
            reputation__gt=0
        ).aggregate(avg=Sum('reputation'))['avg'] or 0
        
        if total_users_with_rep > 0:
            avg_reputation = avg_reputation / total_users_with_rep
        
        # Get top contribution type for this user
        top_contribution = ScoreChange.objects.filter(
            score__author=author
        ).values('contribution_type').annotate(
            total_rep=Sum('score_change')
        ).order_by('-total_rep').first()
        
        top_contribution_type = top_contribution['contribution_type'] if top_contribution else 'NONE'
        top_contribution_rep = top_contribution['total_rep'] if top_contribution else 0
        
        data = {
            'user_reputation': user_reputation,
            'percentile': round(percentile, 2),
            'rank': rank,
            'total_users': total_users_with_rep,
            'avg_reputation': round(avg_reputation, 2),
            'top_contribution_type': top_contribution_type,
            'top_contribution_rep': top_contribution_rep,
        }
        
        serializer = ReputationStatsSerializer(data)
        return Response(serializer.data)

