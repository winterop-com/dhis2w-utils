"""Brand a DHIS2 instance from Python — logos, login-page copy, optional theme CSS.

Uses `Dhis2Client.customize` which wraps DHIS2's three branding endpoint families
(`/api/staticContent/*`, `/api/files/style`, `/api/systemSettings/*`) in a single
accessor, plus a declarative `LoginCustomization` preset for bulk application.

Usage:
    uv run python examples/client/customize_login.py
"""

from __future__ import annotations

from pathlib import Path

from _runner import run_example
from dhis2w_client import LoginCustomization
from dhis2w_core.client_context import open_client
from dhis2w_core.profile import profile_from_env

LOGIN_DIR = Path(__file__).resolve().parents[2] / "infra" / "login-customization"


async def main() -> None:
    """Apply the committed preset + demonstrate the individual accessor methods."""
    async with open_client(profile_from_env()) as client:
        # 1. Bulk: apply the committed preset (logos + settings) in one call.
        preset = LoginCustomization(
            logo_front=(LOGIN_DIR / "logo_front.png").read_bytes(),
            logo_banner=(LOGIN_DIR / "logo_banner.png").read_bytes(),
            system_settings={
                "applicationTitle": "dhis2-utils local",
                "keyApplicationIntro": "Seeded fixture — admin / district credentials.",
                "keyApplicationNotification": "Development instance.",
                "keyApplicationFooter": "Powered by dhis2-utils",
            },
        )
        result = await client.customize.apply_preset(preset)
        print(f"preset applied: {result.model_dump()}")

        # 2. Individual settings — same effect, one at a time.
        await client.customize.set_system_setting("applicationTitle", "dhis2-utils local")

        # 3. Read back what the login app will render (/api/loginConfig).
        config = await client.customize.get_login_config()
        print(f"applicationTitle: {config.applicationTitle}")
        print(f"useCustomLogoFront: {config.useCustomLogoFront}")


if __name__ == "__main__":
    run_example(main)
