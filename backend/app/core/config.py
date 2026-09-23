from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    secret_key: str = "change-me-in-.env"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 14
    database_url: str = "sqlite:///./app.db"
    tmap_app_key: str = ""
    security_light_api_key: str = ""
    kakao_rest_api_key: str = ""
    # 콤마로 구분된 허용 origin 목록. 개발 중 터널(cloudflared 등)로 외부 공유할 때
    # 여기에 프론트 공개 주소를 추가한다. "*"를 쓰면 모든 origin을 허용한다(테스트용).
    cors_allow_origins: str = "http://localhost:3000"
    # dong_code 접두사로 조회 범위를 좁힌다. 예: "41"=경기도, "11"=서울.
    # 빈 문자열이면 전체(서울+경기)를 그대로 쓴다. 발표 시연처럼 특정 지역만
    # 보여줄 때 데이터를 지우지 않고 .env에서만 켜고 끌 수 있게 하는 용도.
    region_scope_prefix: str = ""

    class Config:
        env_file = ".env"


settings = Settings()
