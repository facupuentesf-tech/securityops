"""Optional local Chrome smoke test using a disposable database."""
import subprocess
from pathlib import Path

from test_incidents import IncidentTests


if __name__ == "__main__":
    fixture = IncidentTests(methodName="test_creation_listing_lookup_and_health")
    try:
        fixture.setUp()
        subprocess.run(
            ["node", str(Path(__file__).with_name("browser_smoke.cjs")), fixture.base_url],
            check=True, timeout=120,
        )
    finally:
        fixture.doCleanups()
