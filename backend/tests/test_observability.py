def test_route_metrics_use_only_fixed_labels():
    from app.observability import create_metrics

    metrics = create_metrics()
    metrics.record_route(
        status_code=200,
        duration_seconds=0.25,
        mode="straight_line",
        fallback_reason="tmap_unavailable",
    )
    rendered = metrics.render().decode()

    assert 'route_requests_total{fallback_reason="tmap_unavailable",mode="straight_line"} 1.0' in rendered
    assert "37.50000" not in rendered
    assert "secret-token" not in rendered


def test_metrics_endpoint_exposes_prometheus_content():
    from fastapi.testclient import TestClient
    from app.main import app

    response = TestClient(app).get("/metrics")

    assert response.status_code == 200
    assert "route_duration_seconds" in response.text
