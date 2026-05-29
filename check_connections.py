"""Verify that both Apify and OpenRouter credentials work."""
from clients import check_apify, check_openrouter


def main() -> None:
    print("Checking Apify...")
    try:
        print("  OK ->", check_apify())
    except Exception as e:  # noqa: BLE001
        print("  FAILED ->", repr(e))

    print("Checking OpenRouter...")
    try:
        print("  OK ->", check_openrouter())
    except Exception as e:  # noqa: BLE001
        print("  FAILED ->", repr(e))


if __name__ == "__main__":
    main()
