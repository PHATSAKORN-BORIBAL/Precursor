import pytest

from precursor.config import load_settings
from precursor.service import PrecursorService
from precursor.simulator import PumpRigSimulator
from precursor.vault import Vault


@pytest.fixture(scope="session")
def settings():
    return load_settings()


@pytest.fixture()
def service(settings):
    svc = PrecursorService(settings, Vault(":memory:"))
    yield svc
    svc.close()


def run_scenario(settings, fault=None, seed=7, fault_at=400.0, length=1000, severity=1.0,
                 jitter=0.1):
    """Simulate a run and return the service that ingested it."""
    svc = PrecursorService(settings, Vault(":memory:"))
    sim = PumpRigSimulator(settings, seed=seed, jitter=jitter)
    if fault:
        sim.inject(fault, at=fault_at, severity=severity)
    for sample in sim.stream(length):
        svc.ingest(sample)
    return svc
