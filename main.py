import os

from hotstream.server import run_server


def main():
    port = int(os.getenv("PORT", "5173"))
    run_server(port=port)


if __name__ == "__main__":
    main()
