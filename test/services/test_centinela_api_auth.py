import unittest

from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from app import asgi
from app.config import config
from app.controllers import base


class TestCentinelaAPIAuthentication(unittest.TestCase):
    def setUp(self):
        self.original_app_config = dict(config.app)
        self.client = TestClient(asgi.app)

    def tearDown(self):
        config.app.clear()
        config.app.update(self.original_app_config)

    def test_every_v1_route_has_verify_token_dependency(self):
        checked = 0

        for route in asgi.app.routes:
            if not isinstance(route, APIRoute):
                continue

            if not route.path.startswith("/api/v1"):
                continue

            checked += 1

            dependency_calls = [
                dependency.call
                for dependency in route.dependant.dependencies
            ]

            self.assertIn(
                base.verify_token,
                dependency_calls,
                route.path,
            )

        self.assertGreater(checked, 10)

    def test_empty_key_keeps_centinela_v1_open(self):
        config.app["api_key"] = ""

        response = self.client.get(
            "/api/v1/v1-readiness-audit/health"
        )

        self.assertEqual(
            response.status_code,
            200,
        )

    def test_configured_key_protects_centinela_v1(self):
        config.app["api_key"] = "centinela-test-secret"

        route = "/api/v1/v1-readiness-audit/health"

        missing = self.client.get(route)

        wrong = self.client.get(
            route,
            headers={"x-api-key": "wrong"},
        )

        accepted = self.client.get(
            route,
            headers={
                "x-api-key": "centinela-test-secret"
            },
        )

        self.assertEqual(missing.status_code, 401)
        self.assertEqual(wrong.status_code, 401)
        self.assertEqual(accepted.status_code, 200)

    def test_ping_and_openapi_remain_public(self):
        config.app["api_key"] = "centinela-test-secret"

        self.assertEqual(
            self.client.get("/ping").status_code,
            200,
        )

        self.assertEqual(
            self.client.get("/openapi.json").status_code,
            200,
        )

    def test_ping_has_no_verify_token_dependency(self):
        routes = [
            route
            for route in asgi.app.routes
            if isinstance(route, APIRoute)
            and route.path == "/ping"
        ]

        self.assertEqual(len(routes), 1)

        dependencies = [
            dependency.call
            for dependency in routes[0].dependant.dependencies
        ]

        self.assertNotIn(
            base.verify_token,
            dependencies,
        )

    def test_duplicate_key_headers_are_rejected(self):
        config.app["api_key"] = "centinela-test-secret"

        response = self.client.get(
            "/api/v1/v1-readiness-audit/health",
            headers=[
                (
                    "x-api-key",
                    "centinela-test-secret",
                ),
                (
                    "x-api-key",
                    "wrong",
                ),
            ],
        )

        self.assertEqual(
            response.status_code,
            401,
        )


if __name__ == "__main__":
    unittest.main()