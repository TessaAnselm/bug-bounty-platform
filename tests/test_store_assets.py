import asyncio
from uuid import uuid4

import src.activities.storage.store_assets as store_assets_module
from src.db.models import Asset, AssetStatus, AssetType, Program, ProgramStatus


class _ScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _FakeSession:
    assets: list[Asset] = []
    programs: dict[str, Program] = {}

    def __init__(self, _engine):
        self._pending: list[Asset] = []

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False

    def get(self, model, model_id):
        if model is Program:
            return self.programs.get(str(model_id))
        return None

    def execute(self, stmt):
        params = stmt.compile().params
        program_id = params.get("program_id_1")
        asset_type = params.get("type_1")
        value = params.get("value_1")

        match = next(
            (
                asset
                for asset in self.assets
                if asset.program_id == program_id
                and asset.type == asset_type
                and asset.value == value
            ),
            None,
        )
        return _ScalarResult(match)

    def add(self, obj):
        if isinstance(obj, Asset):
            self._pending.append(obj)

    def flush(self):
        for asset in self._pending:
            if asset.id is None:
                asset.id = uuid4()
            if asset not in self.assets:
                self.assets.append(asset)
        self._pending = []

    def commit(self):
        self.flush()


def _install_fake_session(monkeypatch):
    _FakeSession.assets = []
    _FakeSession.programs = {}
    monkeypatch.setattr(store_assets_module, "Session", _FakeSession)
    monkeypatch.setattr(store_assets_module, "engine", object())
    return _FakeSession


def _probe(value, status=200, technologies=None, source_tool="test"):
    return {
        "input": value,
        "status_code": status,
        "technologies": technologies or [],
        "port": "443",
        "source_tool": source_tool,
    }


def test_store_assets_rejects_out_of_scope_before_db_write(monkeypatch):
    fake = _install_fake_session(monkeypatch)

    asset_ids = asyncio.run(
        store_assets_module.store_assets(
            "program-1",
            "run-1",
            [
                _probe("api.example.com"),
                _probe("admin.example.com"),
            ],
            ["*.example.com"],
            ["admin.example.com"],
        )
    )

    assert len(asset_ids) == 1
    assert [asset.value for asset in fake.assets] == ["api.example.com"]


def test_store_assets_rejects_everything_when_scope_is_empty(monkeypatch):
    fake = _install_fake_session(monkeypatch)

    asset_ids = asyncio.run(
        store_assets_module.store_assets(
            "program-1",
            "run-1",
            [_probe("api.example.com")],
            [],
            [],
        )
    )

    assert asset_ids == []
    assert fake.assets == []


def test_store_assets_updates_existing_asset_instead_of_creating_duplicate(monkeypatch):
    fake = _install_fake_session(monkeypatch)

    first_ids = asyncio.run(
        store_assets_module.store_assets(
            "program-1",
            "run-1",
            [_probe("api.example.com", status=200, technologies=["nginx"], source_tool="subfinder")],
            ["*.example.com"],
            [],
        )
    )
    second_ids = asyncio.run(
        store_assets_module.store_assets(
            "program-1",
            "run-2",
            [_probe("api.example.com", status=403, technologies=["Django", "JWT"], source_tool="httpx")],
            ["*.example.com"],
            [],
        )
    )

    assert first_ids == second_ids
    assert len(fake.assets) == 1

    asset = fake.assets[0]
    assert asset.status == AssetStatus.active
    assert asset.type == AssetType.subdomain
    assert asset.value == "api.example.com"
    assert asset.is_new is False
    assert asset.http_status == 403
    assert asset.technologies == ["Django", "JWT"]
    assert asset.source_tool == "httpx"
    assert "api" in asset.tags
    assert "auth" in asset.tags
    assert asset.risk_score > 0


def test_load_program_scope_rejects_non_active_program(monkeypatch):
    fake = _install_fake_session(monkeypatch)
    program = Program(
        id=uuid4(),
        name="Paused Program",
        platform="hackerone",
        scope=["*.example.com"],
        out_of_scope=[],
        status=ProgramStatus.paused,
    )
    fake.programs[str(program.id)] = program

    try:
        asyncio.run(store_assets_module.load_program_scope(str(program.id)))
    except Exception as exc:
        assert "is not active" in str(exc)
    else:
        raise AssertionError("paused program should reject recon scope loading")
