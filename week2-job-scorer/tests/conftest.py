"""Shared pytest configuration and fixtures."""


def pytest_addoption(parser):
    """Register custom pytest flags."""
    parser.addoption("--run-eval", action="store_true", default=False, help="Run evaluation tests")
    parser.addoption("--run-fetch", action="store_true", default=False, help="Run fetch integration tests")
