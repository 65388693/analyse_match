import math
import unittest
from unittest.mock import patch

import api_client
import live_football_client
import main
from markets import compute_all_markets
from markets_extended import market_corners
from poisson_model import analyze_with_lambdas


class MarketConsistencyTests(unittest.TestCase):
    def test_score_derived_markets_are_normalized(self):
        analysis = analyze_with_lambdas(1.42, 0.91)
        markets = compute_all_markets(
            analysis["matrix"], analysis["lambda_dom"], analysis["lambda_ext"]
        )

        self.assertAlmostEqual(sum(markets["1X2"].values()), 1.0, places=9)
        self.assertAlmostEqual(sum(markets["total_parity"].values()), 1.0, places=9)
        self.assertAlmostEqual(sum(markets["draw_no_bet"].values()), 1.0, places=9)
        self.assertAlmostEqual(sum(markets["total_exact"].values()), 1.0, places=9)
        self.assertAlmostEqual(
            sum(markets["winning_margin"].values()) + markets["1X2"]["nul"],
            1.0,
            places=9,
        )

    def test_corner_over_under_pairs_are_complements(self):
        corners = market_corners(
            {"corners_avg": 4.8},
            {"corners_avg": 5.2},
        )
        for line in ("7_5", "8_5", "9_5", "10_5", "11_5"):
            self.assertAlmostEqual(
                corners[f"over_{line}"] + corners[f"under_{line}"],
                1.0,
                places=12,
            )


class CachedAnalysisTests(unittest.TestCase):
    def test_cached_analysis_never_calls_network(self):
        team_home = {
            "team": "Home",
            "xg_avg": 1.4,
            "xg_against_avg": 1.1,
            "corners_avg": 5.0,
            "matches": [],
            "buts_marques_moy": 1.3,
            "buts_encaisses_moy": 1.0,
            "forme_lignes": [],
            "forme_str": "2V-2N-1D",
            "played": 5,
            "first_goal_bins": [
                {"time": "0-15", "count": 2},
                {"time": "No Goal", "count": 1},
            ],
        }
        team_away = {
            **team_home,
            "team": "Away",
            "xg_avg": 1.0,
            "first_goal_bins": [
                {"time": "15-30", "count": 1},
                {"time": "No Goal", "count": 1},
            ],
        }
        match = {
            "home_team": "Home",
            "away_team": "Away",
            "match_date": "2026-10-09",
            "time": "19:00",
            "real_league_name": "Test League",
            "country": "Test",
            "analysis_league_key": "test1",
            "source_match_id": "offline-test",
            "penalty_score": None,
        }

        with (
            patch.object(main, "get_cached_team_full", side_effect=[team_home, team_away]),
            patch.object(api_client, "call_mcp", side_effect=AssertionError("unexpected Football-Charts request")),
            patch.object(live_football_client, "_call", side_effect=AssertionError("unexpected Live Football request")),
        ):
            result = main.analyze_match_cached("test1", match)

        self.assertIsNotNone(result)
        self.assertTrue(result["cache_only"])
        self.assertEqual(result["data_sources"]["additional_api_requests"], 0)
        self.assertEqual(result["penalties"]["prediction"], None)
        self.assertTrue(result["goal_timing"]["combined"]["available"])
        self.assertGreater(len(result["extended"]["goals_by_period"]["first_half_score_exact"]), 0)
        self.assertTrue(math.isfinite(result["lambda_home"]))
        self.assertTrue(math.isfinite(result["lambda_away"]))


if __name__ == "__main__":
    unittest.main()
