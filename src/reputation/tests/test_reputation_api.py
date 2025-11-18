"""
API tests for reputation breakdown endpoints.

PR #4: Frontend API - Reputation Breakdown Endpoints
"""

from decimal import Decimal
from django.test import TestCase, override_settings
from django.contrib.contenttypes.models import ContentType
from rest_framework.test import APIClient

from reputation.models import Score, ScoreChange, AlgorithmVariables
from reputation.related_models.contribution_weight import ContributionWeight
from user.tests.helpers import create_random_authenticated_user
from hub.tests.helpers import create_hub
from researchhub_comment.tests.helpers import create_rh_comment


class ReputationBreakdownAPITests(TestCase):
    """Test /api/reputation/breakdown/ endpoint."""
    
    def setUp(self):
        """Set up test data."""
        self.client = APIClient()
        self.user = create_random_authenticated_user("test_user")
        self.author = self.user.author_profile
        self.hub = create_hub()
        self.comment = create_rh_comment(created_by=self.user)
        
        # Create algorithm variables
        self.algorithm_variables, _ = AlgorithmVariables.objects.get_or_create(
            hub=self.hub,
            defaults={'variables': {
                'citations': {'bins': {}},
                'votes': {'value': 1}
            }}
        )
        
        # Authenticate
        self.client.force_authenticate(user=self.user)
    
    def test_breakdown_requires_authentication(self):
        """Endpoint should require authentication."""
        client = APIClient()  # Not authenticated
        response = client.get('/api/reputation/breakdown/', {'user_id': self.user.id})
        
        self.assertEqual(response.status_code, 403)
    
    def test_breakdown_requires_user_id(self):
        """Endpoint should require user_id parameter."""
        response = self.client.get('/api/reputation/breakdown/')
        
        self.assertEqual(response.status_code, 400)
        self.assertIn('error', response.data)
    
    def test_breakdown_returns_correct_structure(self):
        """Endpoint should return correct data structure."""
        response = self.client.get('/api/reputation/breakdown/', {'user_id': self.user.id})
        
        self.assertEqual(response.status_code, 200)
        self.assertIn('total_reputation', response.data)
        self.assertIn('breakdown_by_type', response.data)
        self.assertIn('rsc_summary', response.data)
        self.assertIn('recent_changes', response.data)
    
    @override_settings(TIERED_SCORING_ENABLED=True)
    def test_breakdown_shows_tip_reputation(self):
        """Breakdown should show tips in breakdown."""
        score = Score.get_or_create_score(self.author, self.hub)
        
        # Create tip score change
        ScoreChange.create_score_change_funding(
            score=score,
            rsc_amount=Decimal('10.00'),
            content_type=ContentType.objects.get_for_model(self.comment),
            object_id=self.comment.id,
            contribution_type='TIP_RECEIVED',
        )
        
        response = self.client.get('/api/reputation/breakdown/', {'user_id': self.user.id})
        
        self.assertEqual(response.status_code, 200)
        self.assertIn('TIP_RECEIVED', response.data['breakdown_by_type'])
        self.assertEqual(response.data['breakdown_by_type']['TIP_RECEIVED'], 10)
    
    @override_settings(TIERED_SCORING_ENABLED=True)
    def test_breakdown_shows_rsc_summary(self):
        """RSC summary should show total RSC received."""
        score = Score.get_or_create_score(self.author, self.hub)
        
        # Create multiple RSC flows
        ScoreChange.create_score_change_funding(
            score=score,
            rsc_amount=Decimal('10.00'),
            content_type=ContentType.objects.get_for_model(self.comment),
            object_id=self.comment.id,
            contribution_type='TIP_RECEIVED',
        )
        
        ScoreChange.create_score_change_funding(
            score=score,
            rsc_amount=Decimal('150.00'),
            content_type=ContentType.objects.get_for_model(self.comment),
            object_id=self.comment.id,
            contribution_type='BOUNTY_PAYOUT',
        )
        
        response = self.client.get('/api/reputation/breakdown/', {'user_id': self.user.id})
        
        self.assertEqual(response.status_code, 200)
        rsc_summary = response.data['rsc_summary']
        
        self.assertEqual(float(rsc_summary['tips_received']), 10.0)
        self.assertEqual(float(rsc_summary['bounties_received']), 150.0)
        self.assertEqual(float(rsc_summary['total_rsc_received']), 160.0)
    
    @override_settings(TIERED_SCORING_ENABLED=True)
    def test_breakdown_shows_recent_changes(self):
        """Recent changes should be included."""
        score = Score.get_or_create_score(self.author, self.hub)
        
        # Create some score changes
        for i in range(3):
            ScoreChange.create_score_change_funding(
                score=score,
                rsc_amount=Decimal('10.00'),
                content_type=ContentType.objects.get_for_model(self.comment),
                object_id=self.comment.id,
                contribution_type='TIP_RECEIVED',
            )
        
        response = self.client.get('/api/reputation/breakdown/', {'user_id': self.user.id})
        
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data['recent_changes']), 3)
        
        # Check structure of recent change
        recent = response.data['recent_changes'][0]
        self.assertIn('contribution_type', recent)
        self.assertIn('rsc_amount', recent)
        self.assertIn('reputation_earned', recent)
        self.assertIn('date', recent)


class ReputationHistoryAPITests(TestCase):
    """Test /api/reputation/history/ endpoint."""
    
    def setUp(self):
        """Set up test data."""
        self.client = APIClient()
        self.user = create_random_authenticated_user("test_user")
        self.author = self.user.author_profile
        self.hub = create_hub()
        self.comment = create_rh_comment(created_by=self.user)
        
        AlgorithmVariables.objects.get_or_create(
            hub=self.hub,
            defaults={'variables': {
                'citations': {'bins': {}},
                'votes': {'value': 1}
            }}
        )
        
        self.client.force_authenticate(user=self.user)
    
    def test_history_requires_authentication(self):
        """Endpoint should require authentication."""
        client = APIClient()
        response = client.get('/api/reputation/history/', {'user_id': self.user.id})
        
        self.assertEqual(response.status_code, 403)
    
    def test_history_requires_user_id(self):
        """Endpoint should require user_id parameter."""
        response = self.client.get('/api/reputation/history/')
        
        self.assertEqual(response.status_code, 400)
    
    def test_history_returns_correct_structure(self):
        """Endpoint should return correct data structure."""
        response = self.client.get('/api/reputation/history/', {'user_id': self.user.id})
        
        self.assertEqual(response.status_code, 200)
        self.assertIn('history', response.data)
        self.assertIn('change_over_period', response.data)
        self.assertIn('percent_change', response.data)
    
    def test_history_defaults_to_30_days(self):
        """Should default to 30 days if days parameter not provided."""
        response = self.client.get('/api/reputation/history/', {'user_id': self.user.id})
        
        self.assertEqual(response.status_code, 200)
        # Should have ~30 data points (one per day)
        self.assertGreaterEqual(len(response.data['history']), 25)
        self.assertLessEqual(len(response.data['history']), 35)
    
    def test_history_respects_days_parameter(self):
        """Should respect custom days parameter."""
        response = self.client.get('/api/reputation/history/', {
            'user_id': self.user.id,
            'days': 7
        })
        
        self.assertEqual(response.status_code, 200)
        # Should have ~7 data points
        self.assertGreaterEqual(len(response.data['history']), 5)
        self.assertLessEqual(len(response.data['history']), 10)


class ReputationStatsAPITests(TestCase):
    """Test /api/reputation/stats/ endpoint."""
    
    def setUp(self):
        """Set up test data."""
        self.client = APIClient()
        self.user = create_random_authenticated_user("test_user")
        self.author = self.user.author_profile
        self.hub = create_hub()
        
        AlgorithmVariables.objects.get_or_create(
            hub=self.hub,
            defaults={'variables': {
                'citations': {'bins': {}},
                'votes': {'value': 1}
            }}
        )
        
        self.client.force_authenticate(user=self.user)
    
    def test_stats_requires_authentication(self):
        """Endpoint should require authentication."""
        client = APIClient()
        response = client.get('/api/reputation/stats/', {'user_id': self.user.id})
        
        self.assertEqual(response.status_code, 403)
    
    def test_stats_requires_user_id(self):
        """Endpoint should require user_id parameter."""
        response = self.client.get('/api/reputation/stats/')
        
        self.assertEqual(response.status_code, 400)
    
    def test_stats_returns_correct_structure(self):
        """Endpoint should return correct data structure."""
        response = self.client.get('/api/reputation/stats/', {'user_id': self.user.id})
        
        self.assertEqual(response.status_code, 200)
        self.assertIn('user_reputation', response.data)
        self.assertIn('percentile', response.data)
        self.assertIn('rank', response.data)
        self.assertIn('total_users', response.data)
        self.assertIn('avg_reputation', response.data)
        self.assertIn('top_contribution_type', response.data)
    
    @override_settings(TIERED_SCORING_ENABLED=True)
    def test_stats_shows_top_contribution_type(self):
        """Stats should identify user's top contribution type."""
        score = Score.get_or_create_score(self.author, self.hub)
        
        # Create bounty payout (will be highest)
        ScoreChange.create_score_change_funding(
            score=score,
            rsc_amount=Decimal('150.00'),
            content_type=ContentType.objects.get_for_model(self.comment),
            object_id=1,
            contribution_type='BOUNTY_PAYOUT',
        )
        
        # Create smaller tip
        ScoreChange.create_score_change_funding(
            score=score,
            rsc_amount=Decimal('10.00'),
            content_type=ContentType.objects.get_for_model(self.comment),
            object_id=1,
            contribution_type='TIP_RECEIVED',
        )
        
        response = self.client.get('/api/reputation/stats/', {'user_id': self.user.id})
        
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['top_contribution_type'], 'BOUNTY_PAYOUT')


class ReputationAPIEdgeCasesTests(TestCase):
    """Test edge cases for reputation API."""
    
    def setUp(self):
        """Set up test data."""
        self.client = APIClient()
        self.user = create_random_authenticated_user("test_user")
        self.client.force_authenticate(user=self.user)
    
    def test_breakdown_with_no_reputation(self):
        """Should handle users with no reputation gracefully."""
        response = self.client.get('/api/reputation/breakdown/', {'user_id': self.user.id})
        
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['total_reputation'], 0)
        self.assertEqual(len(response.data['breakdown_by_type']), 0)
    
    def test_breakdown_with_invalid_user_id(self):
        """Should return 404 for non-existent user."""
        response = self.client.get('/api/reputation/breakdown/', {'user_id': 99999})
        
        self.assertEqual(response.status_code, 404)
    
    def test_history_with_no_changes(self):
        """History should work even with no score changes."""
        response = self.client.get('/api/reputation/history/', {
            'user_id': self.user.id,
            'days': 7
        })
        
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['change_over_period'], 0)
        self.assertEqual(response.data['percent_change'], 0.0)

