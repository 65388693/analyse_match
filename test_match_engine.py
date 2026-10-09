import math
import os
import tempfile
import unittest
from unittest.mock import patch

import api_client
import daily_picks
import live_football_client
import main
import odds_client
import prediction_store
from data_cleaner import extract_team_data
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

    def test_team_goal_averages_respect_home_and_away_venue(self):
        team = extract_team_data({
            "structuredContent": {
                "team": "Home Team",
                "matches": [
                    {
                        "home": "Home Team",
                        "away": "First Opponent",
                        "score": "2:1",
                        "venue": "H",
                        "outcome": "W",
                    },
                    {
                        "home": "Second Opponent",
                        "away": "Home Team",
                        "score": "3:1",
                        "venue": "A",
                        "outcome": "L",
                    },
                ],
            },
        })

        self.assertEqual(team["buts_marques_moy"], 1.5)
        self.assertEqual(team["buts_encaisses_moy"], 2.0)


class OddsClientTests(unittest.TestCase):
    def test_resolves_supported_competition_key(self):
        sport = odds_client._resolve_sport(
            {"country": "England", "real_league_name": "Premier League"},
            [{"key": "soccer_epl", "title": "EPL"}],
        )

        self.assertEqual(sport["key"], "soccer_epl")

    def test_extracts_bookmaker_prices_and_best_prices(self):
        event = {
            "home_team": "Home FC",
            "away_team": "Away United",
            "bookmakers": [
                {
                    "title": "Bookmaker A",
                    "markets": [{
                        "key": "h2h",
                        "outcomes": [
                            {"name": "Home FC", "price": 2.1},
                            {"name": "Draw", "price": 3.2},
                            {"name": "Away United", "price": 3.8},
                        ],
                    }],
                },
                {
                    "title": "Bookmaker B",
                    "markets": [{
                        "key": "h2h",
                        "outcomes": [
                            {"name": "Home FC", "price": 2.3},
                            {"name": "Draw", "price": 3.0},
                            {"name": "Away United", "price": 3.6},
                        ],
                    }],
                },
            ],
        }

        bookmakers, best = odds_client._extract_h2h(event)

        self.assertEqual(len(bookmakers), 2)
        self.assertEqual(best, {"home": 2.3, "draw": 3.2, "away": 3.8})

    def test_reports_missing_key_without_network_request(self):
        with patch.object(odds_client, "ODDS_API_KEY", ""):
            result = odds_client.get_match_odds({})

        self.assertFalse(result["available"])
        self.assertIn("non configurée", result["reason"])

    def test_network_error_is_returned_without_raising(self):
        with patch.object(
            odds_client.requests,
            "get",
            side_effect=odds_client.requests.ConnectionError,
        ):
            data, error = odds_client._api_get("/sports", {})

        self.assertIsNone(data)
        self.assertEqual(error, "network_error")

    def test_fresh_sport_odds_cache_skips_provider_request(self):
        with (
            patch.object(odds_client.time, "monotonic", return_value=100.0),
            patch.dict(odds_client._odds_cache, {"soccer_epl": (200.0, [{"id": "cached"}])}),
            patch.object(odds_client, "_api_get", side_effect=AssertionError("unexpected request")),
        ):
            events, error = odds_client._sport_odds("soccer_epl")

        self.assertEqual(events, [{"id": "cached"}])
        self.assertIsNone(error)


class DailyPicksTests(unittest.TestCase):
    @staticmethod
    def _analysis(match_id, home, away):
        return {
            "match": {
                "source_match_id": match_id,
                "home_team": home,
                "away_team": away,
                "league": "Test League",
                "country": "Test",
            },
            "markets": {"1X2": {"dom": 0.60, "nul": 0.25, "ext": 0.15}},
            "data_quality": {"label": "usable"},
        }

    @staticmethod
    def _odds(home, away):
        return {
            "available": True,
            "bookmakers": [
                {"key": "another_book", "name": "Other Book", "home": 9.0, "draw": 9.0, "away": 9.0},
                {"key": "1xbet", "name": "1xBet", "home": 2.0, "draw": 4.5, "away": 8.0},
            ],
        }

    def test_daily_candidates_use_only_1xbet_prices(self):
        odds = self._odds("Alpha", "Beta")
        odds["bookmakers"][1]["away"] = 1.2
        result = daily_picks.build_daily_picks([
            (self._analysis("m1", "Alpha", "Beta"), odds),
        ])

        self.assertEqual(len(result["singles"]), 2)
        self.assertEqual({pick["bookmaker"] for pick in result["singles"]}, {"1xBet"})
        self.assertEqual({pick["odds"] for pick in result["singles"]}, {2.0, 4.5})
        self.assertEqual(len(result["_observations"]), 3)
        away_observation = next(
            item for item in result["_observations"] if item["selection"] == "ext"
        )
        self.assertLess(away_observation["expected_return"], 0)

    def test_combinations_never_repeat_a_team(self):
        fixtures = [
            (self._analysis("m1", "Alpha", "Beta"), self._odds("Alpha", "Beta")),
            (self._analysis("m2", "Alpha", "Gamma"), self._odds("Alpha", "Gamma")),
        ]

        result = daily_picks.build_daily_picks(fixtures)

        all_combos = [
            combo
            for group in result["combos"].values()
            for combo in group
        ]
        self.assertEqual(all_combos, [])
        for combo in all_combos:
            teams = [team.casefold() for leg in combo["legs"] for team in (leg["home_team"], leg["away_team"])]
            self.assertEqual(len(teams), len(set(teams)))

    def test_builds_up_to_five_combos_in_each_odds_tier(self):
        fixtures = [
            (
                self._analysis(f"m{index}", f"Home {index}", f"Away {index}"),
                self._odds(f"Home {index}", f"Away {index}"),
            )
            for index in range(1, 6)
        ]

        result = daily_picks.build_daily_picks(fixtures)

        self.assertEqual(len(result["combos"]["prudent"]), 5)
        self.assertEqual(len(result["combos"]["moyen"]), 5)
        self.assertEqual(len(result["combos"]["grosse_cote"]), 5)

    def test_limited_data_never_enters_daily_combinations(self):
        fixtures = [
            (
                {**self._analysis(f"m{index}", f"Home {index}", f"Away {index}"),
                 "data_quality": {"label": "limited"}},
                self._odds(f"Home {index}", f"Away {index}"),
            )
            for index in range(1, 6)
        ]

        result = daily_picks.build_daily_picks(fixtures)

        self.assertEqual(result["coverage"]["candidate_selections"], 15)
        self.assertEqual(result["coverage"]["combo_eligible_selections"], 0)
        self.assertEqual(result["combos"], {"prudent": [], "moyen": [], "grosse_cote": []})


class PredictionStoreTests(unittest.TestCase):
    def test_prediction_is_settled_and_included_in_observed_metrics(self):
        with tempfile.TemporaryDirectory() as directory:
            database_path = os.path.join(directory, "predictions.sqlite3")
            with patch.object(prediction_store, "PREDICTIONS_DB", database_path):
                observations = [
                    {
                        "match_id": "fixture-1",
                        "home_team": "Home",
                        "away_team": "Away",
                        "competition": "Test League",
                        "country": "Test",
                        "selection": selection,
                        "probability": probability,
                        "odds": odds,
                        "bookmaker": "1xBet",
                        "data_quality": "usable",
                    }
                    for selection, probability, odds in (
                        ("dom", 0.6, 2.1),
                        ("nul", 0.25, 3.2),
                        ("ext", 0.15, 4.0),
                    )
                ]
                saved = prediction_store.save_predictions(
                    "2026-10-09",
                    [{
                        "match_id": "fixture-1",
                        "home_team": "Home",
                        "away_team": "Away",
                        "competition": "Test League",
                        "country": "Test",
                        "selection": "dom",
                        "probability": 0.6,
                        "odds": 2.1,
                        "bookmaker": "1xBet",
                        "data_quality": "usable",
                    }],
                    "test-model-v1",
                    observations=observations,
                )
                saved_again = prediction_store.save_predictions(
                    "2026-10-09",
                    [{
                        "match_id": "fixture-1",
                        "home_team": "Home",
                        "away_team": "Away",
                        "competition": "Test League",
                        "country": "Test",
                        "selection": "dom",
                        "probability": 0.6,
                        "odds": 2.15,
                        "bookmaker": "1xBet",
                        "data_quality": "usable",
                    }],
                    "test-model-v1",
                    observations=observations,
                )
                settled = prediction_store.settle_finished_predictions([{
                    "source_match_id": "fixture-1",
                    "match_date": "2026-10-09",
                    "status": "finished",
                    "score": "2-1",
                }])
                stats = prediction_store.get_prediction_stats()

        self.assertEqual(saved, {"model_predictions": 3, "simple_bets": 1})
        self.assertEqual(saved_again, {"model_predictions": 0, "simple_bets": 0})
        self.assertEqual(settled, 4)
        self.assertEqual(stats["total_predictions"], 1)
        self.assertEqual(stats["settled_predictions"], 1)
        self.assertEqual(stats["wins"], 1)
        self.assertAlmostEqual(stats["hit_rate"], 1.0)
        self.assertAlmostEqual(stats["brier_score"], 0.245)
        self.assertEqual(stats["settled_simple_bets"], 1)
        self.assertAlmostEqual(stats["flat_stake_yield"], 1.1)

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
