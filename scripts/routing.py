"""Route enrichment providers and estimate fallback logic."""

from __future__ import annotations

import json
import math
import os
import tempfile
import time
import urllib.parse
import urllib.request
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable


KNOWN_COORDS = {
    "合肥": (117.2272, 31.8206),
    "岳阳": (113.1289, 29.3571),
    "韶山": (112.5253, 27.9150),
    "凤凰": (109.5983, 27.9480),
    "凤凰古城": (109.5983, 27.9480),
    "荔波": (107.8860, 25.4102),
    "小七孔": (107.7170, 25.2580),
    "中国天眼": (106.8567, 25.6529),
    "天眼": (106.8567, 25.6529),
    "安顺": (105.9476, 26.2531),
    "黄果树": (105.6692, 25.9900),
    "贵阳": (106.6302, 26.6477),
    "茅台": (106.3822, 27.8162),
    "茅台镇": (106.3822, 27.8162),
    "茅台镇红军桥": (106.3863, 27.8204),
    "遵义": (106.9274, 27.7257),
    "遵义会议遗址": (106.9271, 27.6931),
    "重庆": (106.5516, 29.5630),
    "重庆市": (106.5516, 29.5630),
    "荆州": (112.2419, 30.3348),
}
ESTIMATED_TOLL_CNY_PER_KM = 0.5
CACHE_LOCK_TIMEOUT_SECONDS = 5.0
CACHE_STALE_LOCK_SECONDS = 30.0
AMAP_MAX_ATTEMPTS = 3
AMAP_RETRY_BASE_SECONDS = 0.4
AMAP_RETRY_ERRORS = (OSError, ValueError, TypeError, KeyError, IndexError)


def amap_key() -> str | None:
    for key_name in ("AMAP_KEY", "GAODE_KEY"):
        value = os.getenv(key_name)
        if value and "your-gaode" not in value:
            return value
    return None


def load_dotenv(path: Path) -> None:
    """Load simple KEY=VALUE lines from .env without overriding the process env."""
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


FetchJson = Callable[[str, dict[str, str]], dict[str, Any]]
Point = tuple[float, float]


def is_finite_number(value: Any) -> bool:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def is_valid_point(value: Any) -> bool:
    return bool(
        isinstance(value, (list, tuple))
        and len(value) == 2
        and is_finite_number(value[0])
        and is_finite_number(value[1])
        and -180 <= value[0] <= 180
        and -90 <= value[1] <= 90
    )


def is_valid_amap_route(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    if value.get("source") != "amap" or not isinstance(value.get("estimated"), bool):
        return False
    for key in ("distance_km", "duration_min"):
        if not is_finite_number(value.get(key)) or value[key] <= 0:
            return False
    if not is_finite_number(value.get("toll_cny")) or value["toll_cny"] < 0:
        return False
    polyline = value.get("polyline")
    return bool(
        isinstance(polyline, list)
        and len(polyline) >= 2
        and all(is_valid_point(point) for point in polyline)
    )


def fetch_json(url: str, params: dict[str, str]) -> dict[str, Any]:
    query = urllib.parse.urlencode(params)
    request = urllib.request.Request(f"{url}?{query}", headers={"User-Agent": "codex-self-drive-trip-planner/1.0"})
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


class JsonRouteCache:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.data = self._load()

    def _load(self) -> dict[str, Any]:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            if (
                isinstance(raw, dict)
                and raw.get("schema_version") == 1
                and isinstance(raw.get("geocode"), dict)
                and isinstance(raw.get("routes"), dict)
            ):
                return {
                    "schema_version": 1,
                    "geocode": dict(raw["geocode"]),
                    "routes": dict(raw["routes"]),
                }
        except Exception:
            pass
        return {"schema_version": 1, "geocode": {}, "routes": {}}

    @contextmanager
    def _write_lock(self):
        lock_path = self.path.with_name(self.path.name + ".lock")
        deadline = time.monotonic() + CACHE_LOCK_TIMEOUT_SECONDS
        fd = None
        while fd is None:
            try:
                fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            except FileExistsError:
                try:
                    if time.time() - lock_path.stat().st_mtime > CACHE_STALE_LOCK_SECONDS:
                        lock_path.unlink()
                        continue
                except FileNotFoundError:
                    continue
                if time.monotonic() >= deadline:
                    raise TimeoutError(f"timed out waiting for route cache lock: {lock_path}")
                time.sleep(0.02)
        try:
            yield
        finally:
            os.close(fd)
            try:
                lock_path.unlink()
            except FileNotFoundError:
                pass

    def save(self) -> None:
        tmp_path = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self._write_lock():
                merged = self._load()
                merged["geocode"].update(self.data["geocode"])
                merged["routes"].update(self.data["routes"])
                with tempfile.NamedTemporaryFile(
                    mode="w",
                    encoding="utf-8",
                    dir=self.path.parent,
                    prefix=self.path.name + ".",
                    suffix=".tmp",
                    delete=False,
                ) as tmp_file:
                    json.dump(merged, tmp_file, ensure_ascii=False, indent=2, sort_keys=True)
                    tmp_file.flush()
                    os.fsync(tmp_file.fileno())
                    tmp_path = Path(tmp_file.name)
                tmp_path.replace(self.path)
                tmp_path = None
                self.data = merged
        except OSError:
            pass
        finally:
            if tmp_path is not None:
                try:
                    tmp_path.unlink()
                except FileNotFoundError:
                    pass

    @staticmethod
    def route_key(origin: Point, destination: Point) -> str:
        return f"{origin[0]:.6f},{origin[1]:.6f}->{destination[0]:.6f},{destination[1]:.6f}"

    def get_geocode(self, place: str) -> Point | None:
        value = self.data["geocode"].get(place)
        if not is_valid_point(value):
            return None
        return (float(value[0]), float(value[1]))

    def set_geocode(self, place: str, point: Point | None) -> None:
        if point is None or not is_valid_point(point):
            return
        self.data["geocode"][place] = [float(point[0]), float(point[1])]
        self.save()

    def get_route(self, origin: Point, destination: Point) -> dict[str, Any] | None:
        value = self.data["routes"].get(self.route_key(origin, destination))
        if not is_valid_amap_route(value):
            return None
        return json.loads(json.dumps(value))

    def set_route(self, origin: Point, destination: Point, metrics: dict[str, Any] | None) -> None:
        if not is_valid_amap_route(metrics):
            return
        self.data["routes"][self.route_key(origin, destination)] = json.loads(json.dumps(metrics))
        self.save()


def route_cache_from_env() -> JsonRouteCache | None:
    value = os.getenv("SDTP_ROUTE_CACHE")
    if not value:
        return None
    return JsonRouteCache(Path(value))


def geocode(
    place: str,
    key: str | None,
    cache: dict[str, Point | None],
    fetcher: FetchJson | None = None,
) -> Point | None:
    if place in cache:
        return cache[place]

    if place in KNOWN_COORDS:
        cache[place] = KNOWN_COORDS[place]
        return cache[place]

    if not key:
        cache[place] = None
        return None

    fetch = fetcher or fetch_json
    last_error = "empty geocode response"
    for attempt in range(AMAP_MAX_ATTEMPTS):
        try:
            payload = fetch(
                "https://restapi.amap.com/v3/geocode/geo",
                {"key": key, "address": place, "output": "json"},
            )
            if not isinstance(payload, dict):
                raise ValueError("response must be an object")
            geocodes = payload.get("geocodes") or []
            if payload.get("status") != "1" or not isinstance(geocodes, list) or not geocodes:
                raise ValueError(payload.get("info") or payload.get("infocode") or "empty geocode response")
            first = geocodes[0]
            if not isinstance(first, dict) or not isinstance(first.get("location"), str):
                raise ValueError("missing geocode location")
            parts = first["location"].split(",")
            if len(parts) != 2:
                raise ValueError("invalid geocode location")
            point = (float(parts[0]), float(parts[1]))
            if not is_valid_point(point):
                raise ValueError("invalid geocode coordinates")
            cache[place] = point
            return point
        except AMAP_RETRY_ERRORS as exc:
            last_error = str(exc) or exc.__class__.__name__
        if attempt < AMAP_MAX_ATTEMPTS - 1:
            time.sleep(AMAP_RETRY_BASE_SECONDS * (attempt + 1))
    raise RuntimeError(f"amap geocode failed for {place} after {AMAP_MAX_ATTEMPTS} attempts: {last_error}")


def parse_polyline(steps: list[dict[str, Any]]) -> list[list[float]]:
    points: list[list[float]] = []
    for step in steps:
        for pair in (step.get("polyline") or "").split(";"):
            if not pair:
                continue
            lng, lat = pair.split(",")[:2]
            points.append([float(lng), float(lat)])
    return points


def route_with_amap(
    origin: Point,
    destination: Point,
    key: str,
    fetcher: FetchJson | None = None,
) -> dict[str, Any] | None:
    last_error = "empty route response"
    fetch = fetcher or fetch_json
    for attempt in range(AMAP_MAX_ATTEMPTS):
        try:
            payload = fetch(
                "https://restapi.amap.com/v3/direction/driving",
                {
                    "key": key,
                    "origin": f"{origin[0]},{origin[1]}",
                    "destination": f"{destination[0]},{destination[1]}",
                    "extensions": "all",
                    "output": "json",
                },
            )
            if not isinstance(payload, dict):
                raise ValueError("response must be an object")
            route = payload.get("route") or {}
            paths = route.get("paths") if isinstance(route, dict) else None
            if payload.get("status") != "1" or not isinstance(paths, list) or not paths:
                raise ValueError(payload.get("info") or payload.get("infocode") or "empty route response")
            path = paths[0]
            if not isinstance(path, dict):
                raise ValueError("route path must be an object")
            distance_m = float(path["distance"])
            duration_seconds = float(path["duration"])
            if not math.isfinite(distance_m) or distance_m <= 0:
                raise ValueError("route distance must be positive and finite")
            if not math.isfinite(duration_seconds) or duration_seconds <= 0:
                raise ValueError("route duration must be positive and finite")
            distance_km = round(distance_m / 1000, 1)
            duration_min = max(1, round(duration_seconds / 60))
            toll_raw = path.get("tolls")
            toll_is_estimated = toll_raw in (None, "")
            toll_cny = (
                round(distance_km * ESTIMATED_TOLL_CNY_PER_KM)
                if toll_is_estimated
                else round(float(toll_raw), 0)
            )
            result = {
                "distance_km": distance_km,
                "duration_min": duration_min,
                "toll_cny": toll_cny,
                "polyline": parse_polyline(path.get("steps") or []),
                "source": "amap",
                "estimated": toll_is_estimated,
            }
            if not is_valid_amap_route(result):
                raise ValueError("incomplete metrics or geometry")
            return result
        except AMAP_RETRY_ERRORS as exc:
            last_error = str(exc) or exc.__class__.__name__
        if attempt < AMAP_MAX_ATTEMPTS - 1:
            time.sleep(AMAP_RETRY_BASE_SECONDS * (attempt + 1))
    raise RuntimeError(f"amap route failed after {AMAP_MAX_ATTEMPTS} attempts: {last_error}")


def haversine_km(a: Point, b: Point) -> float:
    lon1, lat1 = map(math.radians, a)
    lon2, lat2 = map(math.radians, b)
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 6371.0 * 2 * math.asin(math.sqrt(h))


def estimate_route(origin: Point | None, destination: Point | None) -> dict[str, Any]:
    if origin and destination:
        distance_km = round(max(8.0, haversine_km(origin, destination) * 1.35), 1)
        polyline = [[origin[0], origin[1]], [destination[0], destination[1]]]
    else:
        distance_km = 100.0
        polyline = []
    duration_min = max(15, round(distance_km / 72 * 60))
    toll_cny = round(distance_km * ESTIMATED_TOLL_CNY_PER_KM)
    return {
        "distance_km": distance_km,
        "duration_min": duration_min,
        "toll_cny": toll_cny,
        "polyline": polyline,
        "source": "estimated",
        "estimated": True,
    }


class AmapRouteProvider:
    def __init__(
        self,
        key: str | None,
        fetcher: FetchJson | None = None,
        geocode_cache: dict[str, Point | None] | None = None,
        route_cache: JsonRouteCache | None = None,
    ) -> None:
        self.key = key
        self.fetcher = fetcher
        self.geocode_cache = geocode_cache if geocode_cache is not None else {}
        self.route_cache = route_cache

    @property
    def can_route(self) -> bool:
        return bool(self.key)

    def geocode(self, place: str) -> Point | None:
        if place in self.geocode_cache:
            return self.geocode_cache[place]
        if self.route_cache:
            cached = self.route_cache.get_geocode(place)
            if cached is not None:
                self.geocode_cache[place] = cached
                return cached
        point = geocode(place, self.key, self.geocode_cache, self.fetcher)
        if self.route_cache:
            self.route_cache.set_geocode(place, point)
        return point

    def route(self, origin: Point, destination: Point) -> dict[str, Any] | None:
        if not self.key:
            return None
        if self.route_cache:
            cached = self.route_cache.get_route(origin, destination)
            if cached is not None:
                return cached
        metrics = route_with_amap(origin, destination, self.key, self.fetcher)
        if self.route_cache:
            self.route_cache.set_route(origin, destination, metrics)
        return metrics


class EstimateRouteProvider:
    def route(self, origin: Point | None, destination: Point | None) -> dict[str, Any]:
        return estimate_route(origin, destination)


class RouteEnricher:
    def __init__(
        self,
        provider: AmapRouteProvider,
        fallback_provider: EstimateRouteProvider | None = None,
    ) -> None:
        self.provider = provider
        self.fallback_provider = fallback_provider or EstimateRouteProvider()

    def geocode_endpoint(self, leg: dict[str, Any], field: str, errors: list[str]) -> Point | None:
        place = str(leg[field])
        try:
            return self.provider.geocode(place)
        except Exception as exc:
            errors.append(f"geocode {place}: {exc}")
            return None

    def enrich_leg(self, leg: dict[str, Any]) -> None:
        lookup_errors = []
        origin = self.geocode_endpoint(leg, "from", lookup_errors)
        destination = self.geocode_endpoint(leg, "to", lookup_errors)
        metrics = None
        if self.provider.can_route and origin and destination:
            try:
                metrics = self.provider.route(origin, destination)
            except Exception as exc:
                lookup_errors.append(str(exc))
        if metrics is None:
            metrics = self.fallback_provider.route(origin, destination)

        leg.update(metrics)
        if lookup_errors:
            leg["lookup_error"] = " | ".join(lookup_errors)
        leg["origin"] = point_json(origin)
        leg["destination"] = point_json(destination)

    def enrich_days(self, days: list[dict[str, Any]]) -> dict[str, Any]:
        for day in days:
            for leg in day["legs"]:
                self.enrich_leg(leg)
            summarize_day(day)

        totals = {
            "distance_km": round(sum(day["distance_km"] for day in days), 1),
            "duration_min": sum(day["duration_min"] for day in days),
            "toll_cny": round(sum(day["toll_cny"] for day in days), 0),
        }
        return {"days": days, "totals": totals}


def build_route_provider(use_api: bool, key: str | None = None, fetcher: FetchJson | None = None) -> AmapRouteProvider:
    resolved_key = key if key is not None else (amap_key() if use_api else None)
    return AmapRouteProvider(
        resolved_key if use_api else None,
        fetcher=fetcher,
        route_cache=route_cache_from_env(),
    )


def point_json(point: Point | None) -> dict[str, float] | None:
    if not point:
        return None
    return {"lng": point[0], "lat": point[1]}


def summarize_day(day: dict[str, Any]) -> None:
    if not day["legs"]:
        notes = day.get("notes") or ["市区停留"]
        day["title"] = " / ".join(notes)
        day["distance_km"] = 0.0
        day["duration_min"] = 0
        day["toll_cny"] = 0
        day["estimated"] = False
        return

    day["title"] = " → ".join([day["legs"][0]["from"], *[leg["to"] for leg in day["legs"]]])
    day["distance_km"] = round(sum(float(leg["distance_km"]) for leg in day["legs"]), 1)
    day["duration_min"] = sum(int(leg["duration_min"]) for leg in day["legs"])
    day["toll_cny"] = round(sum(float(leg["toll_cny"] or 0) for leg in day["legs"]), 0)
    day["estimated"] = any(bool(leg.get("estimated")) for leg in day["legs"])


def enrich(days: list[dict[str, Any]], use_api: bool, key: str | None = None) -> dict[str, Any]:
    return RouteEnricher(build_route_provider(use_api, key=key)).enrich_days(days)
