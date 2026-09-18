"""Developer text View for generating CSV password data without shell-history input."""

from getpass import getpass

from backend.controllers.passwords import hash_password


def main() -> None:
    try:
        password = getpass("Password to hash: ")
        encoded = hash_password(password)
    except (EOFError, KeyboardInterrupt):
        raise SystemExit("Password entry cancelled.")
    except ValueError as error:
        raise SystemExit(str(error)) from error
    print(encoded)


if __name__ == "__main__":
    main()
