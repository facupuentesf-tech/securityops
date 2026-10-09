"""Run the portfolio walkthrough in Chrome with random, temporary credentials."""
import json
import secrets
import subprocess
from pathlib import Path

from test_incidents import IncidentTests, app_main
import demo


class DemoBrowserFixture(IncidentTests):
    def seed_admin(self):
        self.passwords = {email: secrets.token_urlsafe(24) for _, _, _, email in demo.ACCOUNTS}
        demo.seed_demo(app_main, self.passwords)


if __name__ == "__main__":
    fixture = DemoBrowserFixture(methodName="test_creation_listing_lookup_and_health")
    try:
        fixture.setUp()
        subprocess.run(
            ["node", str(Path(__file__).with_name("browser_smoke.cjs")), fixture.base_url, "--demo"],
            input=json.dumps(fixture.passwords), text=True, check=True, timeout=120,
        )
    finally:
        fixture.doCleanups()
