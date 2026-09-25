"""테스트 수집 전 DB 설정을 고정하고, 각 테스트의 데이터를 격리한다."""

import os
from pathlib import Path

import pytest

_TEST_DATABASE_PATH = Path(__file__).parent / ".test-suite.db"
if _TEST_DATABASE_PATH.exists():
    _TEST_DATABASE_PATH.unlink()

os.environ["DATABASE_URL"] = f"sqlite:///{_TEST_DATABASE_PATH.as_posix()}"
os.environ["APP_ENV"] = "test"
os.environ["REGION_SCOPE_PREFIX"] = ""


@pytest.fixture(autouse=True)
def isolated_database():
    # 이 import들은 환경 변수를 고정한 뒤에 일어나며, 모델 등록도 보장한다.
    from app.db.session import Base, engine
    from app.models import safety_zone, user  # noqa: F401

    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


def pytest_sessionfinish(session, exitstatus):
    from app.db.session import engine

    engine.dispose()
    if _TEST_DATABASE_PATH.exists():
        _TEST_DATABASE_PATH.unlink()
