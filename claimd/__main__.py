"""`python -m claimd` — start the app with HOST/PORT from the environment or .env."""

import uvicorn

from claimd.config import get_settings


def main() -> None:
    settings = get_settings()
    print(f"Claimd → http://{'localhost' if settings.host in ('127.0.0.1', '0.0.0.0') else settings.host}:{settings.port}")
    uvicorn.run("claimd.main:app", host=settings.host, port=settings.port)


if __name__ == "__main__":
    main()
