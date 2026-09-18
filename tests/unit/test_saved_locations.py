"""Unit tests for Saved Locations in Memory & Command Engine Integration."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from denver.automation.weather import GeocodeResult
from denver.commands.models import CommandRequest
from denver.commands.router import IntentRouter
from denver.commands.service import CommandEngineService
from denver.config.settings import DenverSettings
from denver.memory.database import DenverDatabase
from denver.memory.memory_service import MemoryService
from denver.memory.models import SavedLocation
from denver.runtime.event_bus import DenverEventBus
from denver.runtime.state_machine import DenverStateMachine
from denver.runtime.states import DenverState


def test_saved_location_model() -> None:
    loc = SavedLocation(
        label="home",
        raw_address="123 MG Road, Bangalore",
        latitude=12.97,
        longitude=77.59,
    )
    assert loc.label == "home"
    assert loc.latitude == 12.97
    assert loc.created_at is not None
    assert loc.updated_at is not None

    d = loc.to_dict()
    assert d["label"] == "home"
    assert d["raw_address"] == "123 MG Road, Bangalore"


@pytest.mark.asyncio
async def test_saved_locations_crud_and_memory_service(tmp_path) -> None:
    db_file = tmp_path / "test_locations.sqlite3"
    db = DenverDatabase(db_path=str(db_file))
    await db.initialize()

    event_bus = DenverEventBus()
    memory = MemoryService(db=db, event_bus=event_bus)

    # 1. Save location
    saved = await memory.save_location(
        label="Home",
        raw_address="10 Downing Street, London",
        latitude=51.5034,
        longitude=-0.1276,
    )
    assert saved.label == "home"
    assert saved.latitude == 51.5034

    # 2. Get location
    loc = await memory.get_saved_location("home")
    assert loc is not None
    assert loc.raw_address == "10 Downing Street, London"

    # 3. List locations
    await memory.save_location(label="Office", raw_address="Canary Wharf, London")
    locs = await memory.list_saved_locations()
    assert len(locs) == 2
    labels = {l.label for l in locs}
    assert labels == {"home", "office"}

    # 4. Delete location
    deleted = await memory.delete_saved_location("office")
    assert deleted is True
    assert await memory.get_saved_location("office") is None

    await db.close()


@pytest.mark.asyncio
async def test_command_engine_weather_navigation_and_location_intents(tmp_path) -> None:
    db_file = tmp_path / "test_cmd_locations.sqlite3"
    db = DenverDatabase(db_path=str(db_file))
    await db.initialize()

    event_bus = DenverEventBus()
    state_machine = DenverStateMachine(initial_state=DenverState.STANDBY, event_bus=event_bus)
    memory = MemoryService(db=db, event_bus=event_bus)
    settings = DenverSettings(route_open_in_browser=False)

    service = CommandEngineService(
        memory_service=memory,
        state_machine=state_machine,
        event_bus=event_bus,
        settings=settings,
    )

    # 1. Save home location with mocked geocode
    with patch.object(
        service.weather_service,
        "geocode",
        new=AsyncMock(return_value=GeocodeResult(name="London", latitude=51.50, longitude=-0.12)),
    ):
        res1 = await service.process_command("remember this address as home: 10 Downing Street, London")
        assert res1.success is True
        assert "saved home as 10 downing street, london" in res1.message.lower()

    # 2. Query saved home location
    res2 = await service.process_command("what is my saved home address")
    assert res2.success is True
    assert "10 downing street, london" in res2.message.lower()

    # 3. Query weather without specifying city -> auto-resolves to saved home
    with patch.object(
        service.weather_service,
        "get_current_weather",
        new=AsyncMock(return_value=MagicMock(
            source="open-meteo",
            to_spoken_summary=lambda: "In London, it's currently Sunny at 21°C.",
            to_dict=lambda: {"city": "London", "temp_c": 21.0},
        )),
    ):
        res3 = await service.process_command("what is the weather today")
        assert res3.success is True
        assert "21°C" in res3.message

    # 4. Navigate to airport -> auto-resolves origin from saved home
    with patch.object(
        service.navigation_service,
        "calculate_route",
        new=AsyncMock(return_value=MagicMock(
            source="osrm",
            spoken_summary="The fastest route from 10 Downing Street, London to Heathrow Airport is 25 km, taking 45 min by drive.",
            to_dict=lambda: {"formatted_duration": "45 min"},
        )),
    ):
        res4 = await service.process_command("navigate to Heathrow Airport")
        assert res4.success is True
        assert "45 min" in res4.message

    # 5. Delete saved location
    res5 = await service.process_command("forget my saved home location")
    assert res5.success is True
    assert "Removed saved location 'home'" in res5.message

    await db.close()


def test_intent_router_saved_locations() -> None:
    router = IntentRouter()

    i1 = router.route("remember this address as home: 221B Baker Street")
    assert i1.action_name == "save_location"
    assert i1.params["label"] == "home"
    assert i1.params["raw_address"] == "221B Baker Street"

    i2 = router.route("save office as: 1 Infinite Loop")
    assert i2.action_name == "save_location"
    assert i2.params["label"] == "office"

    i3 = router.route("what is my saved office address")
    assert i3.action_name == "get_saved_location"
    assert i3.params["label"] == "office"

    i4 = router.route("list saved locations")
    assert i4.action_name == "get_saved_location"
    assert i4.params["label"] == ""

    i5 = router.route("forget my saved gym location")
    assert i5.action_name == "delete_saved_location"
    assert i5.params["label"] == "gym"
