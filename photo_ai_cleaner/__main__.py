"""Enable ``python -m photo_ai_cleaner`` as an entry point."""

from .main import main

if __name__ == "__main__":
    raise SystemExit(main())
