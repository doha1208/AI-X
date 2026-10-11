from app.core.config import settings


def test_test_database_is_not_created_inside_the_repository():
    assert ".test-suite.db" not in settings.database_url
    assert "pytest-of-" in settings.database_url.replace("\\", "/")
