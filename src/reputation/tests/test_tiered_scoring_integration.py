"""
Tests for tiered scoring integration with ScoreChange.

Tests that create_score_change_votes properly uses ContributionWeight
when the feature flag is enabled.
"""

from django.test import TestCase, override_settings
from django.contrib.contenttypes.models import ContentType

from reputation.models import Score, ScoreChange, AlgorithmVariables
from reputation.related_models.contribution_weight import ContributionWeight
from user.tests.helpers import create_random_authenticated_user
from hub.tests.helpers import create_hub


class TieredScoringIntegrationTests(TestCase):
    """Test tiered scoring integration with score change creation."""
    
    def setUp(self):
        """Set up test data."""
        self.user = create_random_authenticated_user("test_user")
        self.author = self.user.author_profile
        self.hub = create_hub()
        
        # Create algorithm variables
        self.algorithm_variables = AlgorithmVariables.objects.create(
            hub=self.hub,
            variables={
                "vote": {"value": 1},
                "citations": {"bins": {}},
            },
        )
        
        self.score = Score.get_or_create_score(self.author, self.hub)
        self.content_type = ContentType.objects.get_for_model(Score)
    
    @override_settings(TIERED_SCORING_ENABLED=False)
    def test_feature_flag_disabled_uses_old_algorithm(self):
        """When feature flag is disabled, should use old algorithm."""
        score_change = ScoreChange.create_score_change_votes(
            score=self.score,
            raw_value_change=1,
            content_type=self.content_type,
            object_id=self.score.id,
            contribution_type=ContributionWeight.COMMENT,
        )
        
        # Should use old algorithm (1 REP regardless of type)
        self.assertEqual(score_change.score_change, 1)
        # But should still store the contribution type
        self.assertEqual(score_change.contribution_type, ContributionWeight.COMMENT)
    
    @override_settings(TIERED_SCORING_ENABLED=True)
    def test_feature_flag_enabled_uses_tiered_scoring(self):
        """When feature flag is enabled, should use tiered scoring."""
        score_change = ScoreChange.create_score_change_votes(
            score=self.score,
            raw_value_change=1,
            content_type=self.content_type,
            object_id=self.score.id,
            contribution_type=ContributionWeight.COMMENT,
        )
        
        # Should use tiered scoring (COMMENT = 3 REP)
        self.assertEqual(score_change.score_change, 3)
        self.assertEqual(score_change.contribution_type, ContributionWeight.COMMENT)
    
    @override_settings(TIERED_SCORING_ENABLED=True)
    def test_upvote_gets_base_weight(self):
        """Upvote should get weight of 1."""
        score_change = ScoreChange.create_score_change_votes(
            score=self.score,
            raw_value_change=1,
            content_type=self.content_type,
            object_id=self.score.id,
            contribution_type=ContributionWeight.UPVOTE,
        )
        
        self.assertEqual(score_change.score_change, 1)
        self.assertEqual(score_change.contribution_type, ContributionWeight.UPVOTE)
    
    @override_settings(TIERED_SCORING_ENABLED=True)
    def test_downvote_applies_negative_weight(self):
        """Downvote should apply negative reputation."""
        score_change = ScoreChange.create_score_change_votes(
            score=self.score,
            raw_value_change=-1,
            content_type=self.content_type,
            object_id=self.score.id,
            contribution_type=ContributionWeight.DOWNVOTE,
        )
        
        # Should be -1 (negative direction)
        self.assertEqual(score_change.score_change, -1)
        self.assertEqual(score_change.contribution_type, ContributionWeight.DOWNVOTE)
    
    @override_settings(TIERED_SCORING_ENABLED=True)
    def test_peer_review_gets_high_weight(self):
        """Peer review should get weight of 15."""
        score_change = ScoreChange.create_score_change_votes(
            score=self.score,
            raw_value_change=1,
            content_type=self.content_type,
            object_id=self.score.id,
            contribution_type=ContributionWeight.PEER_REVIEW,
        )
        
        self.assertEqual(score_change.score_change, 15)
        self.assertEqual(score_change.contribution_type, ContributionWeight.PEER_REVIEW)
    
    @override_settings(TIERED_SCORING_ENABLED=True)
    def test_score_accumulates_correctly(self):
        """Score should accumulate across multiple contributions."""
        # First contribution: COMMENT (3 REP)
        score_change_1 = ScoreChange.create_score_change_votes(
            score=self.score,
            raw_value_change=1,
            content_type=self.content_type,
            object_id=1,
            contribution_type=ContributionWeight.COMMENT,
        )
        self.assertEqual(score_change_1.score_after_change, 3)
        
        # Second contribution: UPVOTE (1 REP)
        score_change_2 = ScoreChange.create_score_change_votes(
            score=self.score,
            raw_value_change=1,
            content_type=self.content_type,
            object_id=2,
            contribution_type=ContributionWeight.UPVOTE,
        )
        self.assertEqual(score_change_2.score_after_change, 4)  # 3 + 1
        
        # Third contribution: PEER_REVIEW (15 REP)
        score_change_3 = ScoreChange.create_score_change_votes(
            score=self.score,
            raw_value_change=1,
            content_type=self.content_type,
            object_id=3,
            contribution_type=ContributionWeight.PEER_REVIEW,
        )
        self.assertEqual(score_change_3.score_after_change, 19)  # 4 + 15
    
    @override_settings(TIERED_SCORING_ENABLED=True)
    def test_contribution_type_defaults_to_upvote(self):
        """If contribution_type not specified, should default to UPVOTE."""
        score_change = ScoreChange.create_score_change_votes(
            score=self.score,
            raw_value_change=1,
            content_type=self.content_type,
            object_id=self.score.id,
            # contribution_type not specified
        )
        
        # Should default to UPVOTE (weight = 1)
        self.assertEqual(score_change.score_change, 1)
        self.assertEqual(score_change.contribution_type, 'UPVOTE')
    
    @override_settings(TIERED_SCORING_ENABLED=True)
    def test_all_contribution_types_work(self):
        """All contribution types should work correctly."""
        test_cases = [
            (ContributionWeight.UPVOTE, 1),
            (ContributionWeight.DOWNVOTE, 1),
            (ContributionWeight.COMMENT, 3),
            (ContributionWeight.THREAD_CREATED, 5),
            (ContributionWeight.BOUNTY_CREATED, 5),
            (ContributionWeight.POST_CREATED, 10),
            (ContributionWeight.PEER_REVIEW, 15),
            (ContributionWeight.BOUNTY_SOLUTION, 20),
            (ContributionWeight.BOUNTY_FUNDED, 30),
            (ContributionWeight.PAPER_PUBLISHED, 50),
        ]
        
        for idx, (contrib_type, expected_weight) in enumerate(test_cases):
            with self.subTest(contribution_type=contrib_type):
                score_change = ScoreChange.create_score_change_votes(
                    score=self.score,
                    raw_value_change=1,
                    content_type=self.content_type,
                    object_id=100 + idx,
                    contribution_type=contrib_type,
                )
                self.assertEqual(score_change.score_change, expected_weight)
                self.assertEqual(score_change.contribution_type, contrib_type)
    
    @override_settings(
        TIERED_SCORING_ENABLED=True,
        CONTRIBUTION_WEIGHT_OVERRIDES={'COMMENT': 5}
    )
    def test_weight_overrides_work(self):
        """Configuration overrides should be respected."""
        score_change = ScoreChange.create_score_change_votes(
            score=self.score,
            raw_value_change=1,
            content_type=self.content_type,
            object_id=self.score.id,
            contribution_type=ContributionWeight.COMMENT,
        )
        
        # Should use override value (5 instead of 3)
        self.assertEqual(score_change.score_change, 5)
    
    def test_backward_compatibility_with_no_contribution_type(self):
        """Old code calling without contribution_type should still work."""
        # Call without contribution_type parameter (backward compatibility)
        score_change = ScoreChange.create_score_change_votes(
            score=self.score,
            raw_value_change=1,
            content_type=self.content_type,
            object_id=self.score.id,
        )
        
        # Should work and default to UPVOTE
        self.assertIsNotNone(score_change)
        self.assertEqual(score_change.contribution_type, 'UPVOTE')

