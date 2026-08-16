import os

from app import app


def main():
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "5001"))
    debug = os.getenv("FLASK_DEBUG", "false").lower() in {"1", "true", "yes"}

    app.run(host=host, port=port, debug=debug)


if __name__ == "__main__":
    main()
