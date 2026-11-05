"""신뢰 가능한 배치 작업이 만든 안전 경로 산출물의 게시와 로드."""

import hashlib
import json
import logging
import os
import pickle
from dataclasses import dataclass, field
from pathlib import Path

import networkx as nx
import numpy as np

from app.services.safety_score import Period

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 4
ARTIFACT_FILENAME = "route-artifact.pickle"
CURRENT_MANIFEST_FILENAME = "current.json"


@dataclass(frozen=True)
class RouteArtifact:
    """한 데이터 버전의 지역별·낮밤별 안전 가중 경로 그래프."""

    version: str
    region: str
    graph_by_period: dict[Period, nx.DiGraph]
    node_ids: list[int]
    node_points: np.ndarray
    profile_version: str = "default-v1"
    data_version: str = "test-data"
    score_by_period: dict[Period, dict[str, float]] = field(
        default_factory=lambda: {"day": {}, "night": {}}
    )
    schema_version: int = SCHEMA_VERSION
    environment_model_version: str | None = None
    policy_version: str | None = None
    environment_index: object | None = None
    environment_policy_fingerprint: str | None = None
    environment_graph: nx.DiGraph | None = None
    walk_environment_index: object | None = None
    zone_facility_summaries: dict = field(default_factory=dict)
    boundary_version: str | None = None
    sampling_version: str | None = None
    boundary_diagnostics: dict = field(default_factory=dict)


def extended_artifact_valid(artifact) -> bool:
    if artifact.schema_version != 4 or artifact.environment_model_version is None:
        return True
    from app.services.walk_environment_samples import SAMPLING_VERSION, WalkEnvironmentIndex
    index = getattr(artifact, "walk_environment_index", None)
    if not isinstance(index, WalkEnvironmentIndex) or index.sampling_version != SAMPLING_VERSION:
        return False
    if artifact.sampling_version != SAMPLING_VERSION or not artifact.boundary_version:
        return False
    summaries = getattr(artifact, "zone_facility_summaries", None)
    return isinstance(summaries, dict) and len(index._tree.geometries) == len(index.segments)


def _validate_version(version: str) -> None:
    if not version or Path(version).name != version or version in {".", ".."}:
        raise ValueError("Artifact version must be a single non-empty path segment")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json(path: Path, payload: dict) -> None:
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, sort_keys=True)
        f.flush()
        os.fsync(f.fileno())


def _relative_artifact_path(version: str) -> Path:
    return Path(version) / ARTIFACT_FILENAME


def _validate_artifact(artifact: RouteArtifact, manifest: dict) -> bool:
    if not isinstance(artifact, RouteArtifact):
        return False
    actual_schema = artifact.__dict__.get("schema_version", 2)
    if actual_schema != manifest["schema_version"]:
        return False
    if actual_schema == 2 and artifact.__dict__.get("environment_model_version"):
        return False
    if artifact.version != manifest["version"] or artifact.region != manifest["region"]:
        return False
    if artifact.profile_version != manifest["profile_version"] or artifact.data_version != manifest["data_version"]:
        return False
    if set(artifact.graph_by_period) != {"day", "night"}:
        return False
    if set(artifact.score_by_period) != {"day", "night"}:
        return False
    if len(artifact.node_ids) != len(artifact.node_points):
        return False
    if not extended_artifact_valid(artifact):
        return False
    return artifact.node_points.ndim == 2 and artifact.node_points.shape[1] == 2


def publish_artifact(artifact: RouteArtifact, directory: Path, *, validation_report: dict | None = None) -> Path:
    """완성된 산출물을 먼저 저장하고 마지막에 current 매니페스트를 바꾼다."""

    _validate_version(artifact.version)
    if not extended_artifact_valid(artifact):
        raise ValueError("Invalid extended spatial artifact")
    directory.mkdir(parents=True, exist_ok=True)
    version_dir = directory / artifact.version
    temporary_dir = directory / f".{artifact.version}.tmp"
    if version_dir.exists() or temporary_dir.exists():
        raise FileExistsError(f"Artifact version already exists or is incomplete: {artifact.version}")

    temporary_dir.mkdir()
    relative_path = _relative_artifact_path(artifact.version)
    temporary_artifact = temporary_dir / ARTIFACT_FILENAME
    try:
        with temporary_artifact.open("wb") as f:
            pickle.dump(artifact, f, protocol=pickle.HIGHEST_PROTOCOL)
            f.flush()
            os.fsync(f.fileno())

        checksum = _sha256(temporary_artifact)
        if validation_report is not None:
            _write_json(temporary_dir / "validation.json", validation_report)
        _write_json(
            temporary_dir / "metadata.json",
            {
                "schema_version": artifact.schema_version,
                "version": artifact.version,
                "region": artifact.region,
                "artifact_file": str(relative_path).replace("\\", "/"),
                "sha256": checksum,
                "profile_version": artifact.profile_version,
                "data_version": artifact.data_version,
            },
        )
        temporary_dir.replace(version_dir)

        manifest_tmp = directory / ".current.json.tmp"
        _write_json(
            manifest_tmp,
            {
                "schema_version": artifact.schema_version,
                "version": artifact.version,
                "region": artifact.region,
                "artifact_file": str(relative_path).replace("\\", "/"),
                "sha256": checksum,
                "profile_version": artifact.profile_version,
                "data_version": artifact.data_version,
            },
        )
        manifest_tmp.replace(directory / CURRENT_MANIFEST_FILENAME)
    except Exception:
        logger.exception("Failed to publish route artifact version %s", artifact.version)
        raise

    return version_dir


def load_current_artifact(directory: Path) -> RouteArtifact | None:
    """현재 매니페스트가 참조하는 검증된 애플리케이션 산출물만 로드한다."""

    manifest_path = directory / CURRENT_MANIFEST_FILENAME
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        required = {
            "schema_version",
            "version",
            "region",
            "artifact_file",
            "sha256",
            "profile_version",
            "data_version",
        }
        if not isinstance(manifest, dict) or set(manifest) != required:
            raise ValueError("Route artifact manifest fields are invalid")
        if manifest["schema_version"] not in (2, 3, SCHEMA_VERSION):
            raise ValueError("Route artifact manifest schema is unsupported")
        if not all(isinstance(manifest[field], str) and manifest[field] for field in required - {"schema_version"}):
            raise ValueError("Route artifact manifest values are invalid")
        _validate_version(manifest["version"])

        relative_path = Path(manifest["artifact_file"])
        if relative_path.is_absolute() or ".." in relative_path.parts:
            raise ValueError("Route artifact manifest path is unsafe")
        if relative_path != _relative_artifact_path(manifest["version"]):
            raise ValueError("Route artifact manifest path does not match its version")
        artifact_path = directory / relative_path
        if _sha256(artifact_path) != manifest["sha256"]:
            raise ValueError("Route artifact checksum does not match")

        with artifact_path.open("rb") as f:
            artifact = pickle.load(f)
        if not _validate_artifact(artifact, manifest):
            raise ValueError("Route artifact contents do not match its manifest")
        object.__setattr__(artifact, "schema_version", manifest["schema_version"])
        return artifact
    except (OSError, ValueError, TypeError, AttributeError, ImportError, IndexError, EOFError, pickle.PickleError):
        logger.warning("Current route artifact is unavailable or invalid: %s", manifest_path, exc_info=True)
        return None
