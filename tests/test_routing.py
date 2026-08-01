import importlib.util
import json
import os
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "routing.py"


def load_routing():
    spec = importlib.util.spec_from_file_location("routing", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class RoutingTests(unittest.TestCase):
    def setUp(self):
        self.routing = load_routing()
        self.routing.time.sleep = lambda seconds: None

    def test_route_with_amap_parses_metrics_and_polyline(self):
        def fake_fetch_json(url, params):
            self.assertIn("/direction/driving", url)
            self.assertEqual(params["extensions"], "all")
            return {
                "status": "1",
                "route": {
                    "paths": [
                        {
                            "distance": "12345",
                            "duration": "3660",
                            "tolls": "88.4",
                            "steps": [
                                {"polyline": "117.0,31.0;117.5,31.5"},
                                {"polyline": "118.0,32.0"},
                            ],
                        }
                    ]
                },
            }

        self.routing.fetch_json = fake_fetch_json

        result = self.routing.route_with_amap((117.0, 31.0), (118.0, 32.0), "test-key")

        self.assertEqual(result["distance_km"], 12.3)
        self.assertEqual(result["duration_min"], 61)
        self.assertEqual(result["toll_cny"], 88.0)
        self.assertFalse(result["estimated"])
        self.assertEqual(result["source"], "amap")
        self.assertEqual(result["polyline"], [[117.0, 31.0], [117.5, 31.5], [118.0, 32.0]])

    def test_route_with_amap_estimates_missing_toll_as_numeric(self):
        def fake_fetch_json(url, params):
            return {
                "status": "1",
                "route": {
                    "paths": [
                        {
                            "distance": "10000",
                            "duration": "1800",
                            "steps": [{"polyline": "120.0,30.0;121.0,31.0"}],
                        }
                    ]
                },
            }

        result = self.routing.route_with_amap(
            (120.0, 30.0),
            (121.0, 31.0),
            "test-key",
            fetcher=fake_fetch_json,
        )

        self.assertEqual(result["toll_cny"], 5)
        self.assertTrue(result["estimated"])
        self.assertEqual(result["source"], "amap")

    def test_route_with_amap_rejects_incomplete_geometry(self):
        def fake_fetch_json(url, params):
            return {
                "status": "1",
                "route": {
                    "paths": [
                        {
                            "distance": "10000",
                            "duration": "1800",
                            "tolls": "5",
                            "steps": [],
                        }
                    ]
                },
            }

        with self.assertRaisesRegex(RuntimeError, "failed after 3 attempts: incomplete metrics or geometry"):
            self.routing.route_with_amap(
                (120.0, 30.0),
                (121.0, 31.0),
                "test-key",
                fetcher=fake_fetch_json,
            )

    def test_geocode_uses_cache_and_provider_result(self):
        calls = []

        def fake_fetch_json(url, params):
            calls.append((url, params))
            return {"status": "1", "geocodes": [{"location": "120.1,30.2"}]}

        self.routing.fetch_json = fake_fetch_json
        cache = {}

        first = self.routing.geocode("测试地点", "test-key", cache)
        second = self.routing.geocode("测试地点", "test-key", cache)

        self.assertEqual(first, (120.1, 30.2))
        self.assertEqual(second, (120.1, 30.2))
        self.assertEqual(len(calls), 1)

    def test_geocode_rejects_out_of_range_provider_coordinates(self):
        def fake_fetch_json(url, params):
            return {"status": "1", "geocodes": [{"location": "181.0,30.0"}]}

        with self.assertRaisesRegex(RuntimeError, "failed for 错误地点 after 3 attempts: invalid geocode coordinates"):
            self.routing.geocode("错误地点", "test-key", {}, fetcher=fake_fetch_json)

    def test_geocode_retries_transient_failure(self):
        calls = []

        def fake_fetch_json(url, params):
            calls.append(params["address"])
            if len(calls) == 1:
                raise OSError("temporary network failure")
            return {"status": "1", "geocodes": [{"location": "120.1,30.2"}]}

        result = self.routing.geocode("测试地点", "test-key", {}, fetcher=fake_fetch_json)

        self.assertEqual(result, (120.1, 30.2))
        self.assertEqual(calls, ["测试地点", "测试地点"])

    def test_route_with_amap_retries_malformed_success_response(self):
        calls = []

        def fake_fetch_json(url, params):
            calls.append(params["origin"])
            if len(calls) == 1:
                return {
                    "status": "1",
                    "route": {"paths": [{"distance": "0", "duration": "1800", "steps": []}]},
                }
            return {
                "status": "1",
                "route": {
                    "paths": [
                        {
                            "distance": "10000",
                            "duration": "1800",
                            "tolls": "5",
                            "steps": [{"polyline": "120.0,30.0;121.0,31.0"}],
                        }
                    ]
                },
            }

        result = self.routing.route_with_amap(
            (120.0, 30.0),
            (121.0, 31.0),
            "test-key",
            fetcher=fake_fetch_json,
        )

        self.assertEqual(result["distance_km"], 10.0)
        self.assertEqual(len(calls), 2)

    def test_route_enricher_uses_provider_cache_and_amap_routes(self):
        geocode_calls = []
        route_calls = []
        coords = {
            "测试A": "120.0,30.0",
            "测试B": "121.0,31.0",
            "测试C": "122.0,32.0",
        }

        def fake_fetch_json(url, params):
            if "/geocode/geo" in url:
                geocode_calls.append(params["address"])
                return {"status": "1", "geocodes": [{"location": coords[params["address"]]}]}
            if "/direction/driving" in url:
                route_calls.append((params["origin"], params["destination"]))
                return {
                    "status": "1",
                    "route": {
                        "paths": [
                            {
                                "distance": "10000",
                                "duration": "1800",
                                "tolls": "12",
                                "steps": [{"polyline": f"{params['origin']};{params['destination']}"}],
                            }
                        ]
                    },
                }
            raise AssertionError(f"unexpected url: {url}")

        days = [
            {
                "day": "D1",
                "notes": [],
                "legs": [
                    {"from": "测试A", "to": "测试B"},
                    {"from": "测试B", "to": "测试C"},
                ],
            }
        ]
        provider = self.routing.AmapRouteProvider("test-key", fetcher=fake_fetch_json)

        data = self.routing.RouteEnricher(provider).enrich_days(days)

        legs = data["days"][0]["legs"]
        self.assertEqual(geocode_calls, ["测试A", "测试B", "测试C"])
        self.assertEqual(len(route_calls), 2)
        self.assertEqual([leg["source"] for leg in legs], ["amap", "amap"])
        self.assertEqual(data["totals"]["distance_km"], 20.0)
        self.assertEqual(data["totals"]["duration_min"], 60)

    def test_route_enricher_records_lookup_error_and_uses_estimate_fallback(self):
        class FailingProvider:
            can_route = True

            def geocode(self, place):
                return {"合肥": (117.2272, 31.8206), "岳阳": (113.1289, 29.3571)}[place]

            def route(self, origin, destination):
                raise RuntimeError("quota exceeded")

        days = [{"day": "D1", "notes": [], "legs": [{"from": "合肥", "to": "岳阳"}]}]

        data = self.routing.RouteEnricher(FailingProvider()).enrich_days(days)

        leg = data["days"][0]["legs"][0]
        self.assertEqual(leg["source"], "estimated")
        self.assertTrue(leg["estimated"])
        self.assertEqual(leg["lookup_error"], "quota exceeded")

    def test_route_enricher_records_geocode_error_and_uses_estimate_fallback(self):
        class FailingGeocodeProvider:
            can_route = True

            def geocode(self, place):
                raise RuntimeError("geocode quota exceeded")

            def route(self, origin, destination):
                raise AssertionError("route should not be called without coordinates")

        days = [{"day": "D1", "notes": [], "legs": [{"from": "未知A", "to": "未知B"}]}]

        data = self.routing.RouteEnricher(FailingGeocodeProvider()).enrich_days(days)

        leg = data["days"][0]["legs"][0]
        self.assertEqual(leg["source"], "estimated")
        self.assertTrue(leg["estimated"])
        self.assertIsNone(leg["origin"])
        self.assertIn("geocode 未知A", leg["lookup_error"])
        self.assertIn("geocode 未知B", leg["lookup_error"])

    def test_enrich_uses_explicit_key_for_provider(self):
        seen_keys = []

        def fake_fetch_json(url, params):
            self.assertIn("/direction/driving", url)
            seen_keys.append(params["key"])
            return {
                "status": "1",
                "route": {
                    "paths": [
                        {
                            "distance": "10000",
                            "duration": "1800",
                            "tolls": "12",
                            "steps": [{"polyline": "117.2272,31.8206;113.1289,29.3571"}],
                        }
                    ]
                },
            }

        self.routing.fetch_json = fake_fetch_json
        days = [{"day": "D1", "notes": [], "legs": [{"from": "合肥", "to": "岳阳"}]}]

        data = self.routing.enrich(days, use_api=True, key="explicit-key")

        self.assertEqual(seen_keys, ["explicit-key"])
        self.assertEqual(data["days"][0]["legs"][0]["source"], "amap")

    def test_json_route_cache_serves_geocode_and_routes_without_fetching(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = self.routing.JsonRouteCache(Path(tmp) / "routes.json")
            origin = (120.0, 30.0)
            destination = (121.0, 31.0)
            metrics = {
                "distance_km": 12.3,
                "duration_min": 34,
                "toll_cny": 5.0,
                "polyline": [[120.0, 30.0], [121.0, 31.0]],
                "source": "amap",
                "estimated": False,
            }
            cache.set_geocode("测试A", origin)
            cache.set_route(origin, destination, metrics)

            def fail_fetch(url, params):
                raise AssertionError("fetch should not be called for cached data")

            provider = self.routing.AmapRouteProvider(
                "test-key",
                fetcher=fail_fetch,
                route_cache=self.routing.JsonRouteCache(Path(tmp) / "routes.json"),
            )

            self.assertEqual(provider.geocode("测试A"), origin)
            self.assertEqual(provider.route(origin, destination), metrics)

    def test_json_route_cache_does_not_store_failed_routes(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache_path = Path(tmp) / "routes.json"
            cache = self.routing.JsonRouteCache(cache_path)

            def failing_fetch(url, params):
                raise RuntimeError("boom")

            provider = self.routing.AmapRouteProvider("test-key", fetcher=failing_fetch, route_cache=cache)

            with self.assertRaises(RuntimeError):
                provider.route((120.0, 30.0), (121.0, 31.0))

            saved = json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.exists() else {"routes": {}}
            self.assertEqual(saved.get("routes") or {}, {})

    def test_json_route_cache_rejects_invalid_coordinates_and_routes(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache_path = Path(tmp) / "routes.json"
            origin = (120.0, 30.0)
            destination = (121.0, 31.0)
            route_key = self.routing.JsonRouteCache.route_key(origin, destination)
            cache_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "geocode": {
                            "越界": [181.0, 30.0],
                            "非有限": [float("nan"), 30.0],
                        },
                        "routes": {
                            route_key: {
                                "distance_km": 10 ** 1000,
                                "duration_min": 30,
                                "toll_cny": 5.0,
                                "polyline": [[120.0, 30.0], [121.0, 31.0]],
                                "source": "amap",
                                "estimated": False,
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )
            cache = self.routing.JsonRouteCache(cache_path)

            self.assertIsNone(cache.get_geocode("越界"))
            self.assertIsNone(cache.get_geocode("非有限"))
            self.assertIsNone(cache.get_route(origin, destination))

    def test_json_route_cache_ignores_unknown_schema_version(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache_path = Path(tmp) / "routes.json"
            cache_path.write_text(
                json.dumps(
                    {
                        "schema_version": 2,
                        "geocode": {"测试": [120.0, 30.0]},
                        "routes": {},
                    }
                ),
                encoding="utf-8",
            )

            cache = self.routing.JsonRouteCache(cache_path)

            self.assertEqual(cache.data, {"schema_version": 1, "geocode": {}, "routes": {}})

    def test_json_route_cache_merges_concurrent_writers(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache_path = Path(tmp) / "routes.json"
            caches = [self.routing.JsonRouteCache(cache_path) for _ in range(8)]
            barrier = threading.Barrier(len(caches))

            def write_entry(index):
                barrier.wait()
                caches[index].set_geocode(f"地点{index}", (120.0 + index / 10, 30.0))

            with ThreadPoolExecutor(max_workers=len(caches)) as executor:
                list(executor.map(write_entry, range(len(caches))))

            saved = self.routing.JsonRouteCache(cache_path)
            for index in range(len(caches)):
                self.assertEqual(saved.get_geocode(f"地点{index}"), (120.0 + index / 10, 30.0))
            self.assertFalse(cache_path.with_name(cache_path.name + ".lock").exists())
            self.assertEqual(list(cache_path.parent.glob(cache_path.name + ".*.tmp")), [])

    def test_build_route_provider_uses_env_cache_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache_path = Path(tmp) / "routes.json"
            old_value = os.environ.get("SDTP_ROUTE_CACHE")
            os.environ["SDTP_ROUTE_CACHE"] = str(cache_path)
            try:
                provider = self.routing.build_route_provider(True, key="test-key")
            finally:
                if old_value is None:
                    os.environ.pop("SDTP_ROUTE_CACHE", None)
                else:
                    os.environ["SDTP_ROUTE_CACHE"] = old_value

            self.assertIsNotNone(provider.route_cache)
            self.assertEqual(provider.route_cache.path, cache_path)


if __name__ == "__main__":
    unittest.main()
