from pydantic_settings import BaseSettings


DEFAULT_SECRET_KEY = "change-me-in-.env"


class Settings(BaseSettings):
    app_env: str = "development"
    secret_key: str = DEFAULT_SECRET_KEY
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 14
    database_url: str = "sqlite:///./app.db"
    tmap_app_key: str = ""
    security_light_api_key: str = ""
    kakao_rest_api_key: str = ""
    # 쉼표로 구분된 관리자 이메일. 빈 값이면 관리자 API는 모든 사용자에게 거부된다.
    admin_emails: str = ""
    # 콤마로 구분된 허용 origin 목록. 개발 중 터널(cloudflared 등)로 외부 공유할 때
    # 여기에 프론트 공개 주소를 추가한다. "*"를 쓰면 모든 origin을 허용한다(테스트용).
    cors_allow_origins: str = "http://localhost:3000"
    # dong_code 접두사로 조회 범위를 좁힌다. 예: "41"=경기도, "11"=서울.
    # 빈 문자열이면 전체(서울+경기)를 그대로 쓴다. 발표 시연처럼 특정 지역만
    # 보여줄 때 데이터를 지우지 않고 .env에서만 켜고 끌 수 있게 하는 용도.
    region_scope_prefix: str = ""
    # 공공데이터 적재 후 배치가 만드는 신뢰 가능한 경로 산출물 디렉터리.
    route_artifact_dir: str = "data/route_artifacts"
    # 산출물 버전별 경로 결과 LRU 캐시와 매니페스트 재확인 주기.
    route_result_cache_size: int = 2048
    route_artifact_reload_seconds: int = 60
    tmap_route_cache_seconds: int = 300
    # 공개 경로 API 보호 정책. 한 프로세스 안에서 적용한다.
    route_max_concurrent: int = 2
    route_ip_requests_per_minute: int = 30
    route_ip_burst: int = 8
    route_user_requests_per_minute: int = 20
    route_user_burst: int = 5
    route_request_max_tracked_buckets: int = 10_000
    # Caddy가 같은 서버에서 API로 프록시할 때만 전달 IP를 신뢰한다.
    trusted_proxy_ips: str = "127.0.0.1,::1"

    class Config:
        env_file = ".env"


settings = Settings()


def validate_runtime_settings(config: Settings) -> None:
    """운영 계열 환경이 약한 JWT 키로 시작하지 않도록 막는다."""

    if config.app_env.lower() in {"development", "test"}:
        return
    if config.secret_key == DEFAULT_SECRET_KEY or len(config.secret_key) < 32:
        raise RuntimeError("SECRET_KEY must be a random value of at least 32 characters outside development")
