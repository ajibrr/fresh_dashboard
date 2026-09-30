import argparse
import sys
from datetime import datetime
from pathlib import Path

from app.config import load_json
from app.optimizer.optimizer import run_optimize


class _Tee:
    """Mirrors everything written to stdout into a log file as well."""

    def __init__(self, stream, log_file):
        self._stream = stream
        self._log_file = log_file

    def write(self, data):
        self._stream.write(data)
        self._log_file.write(data)

    def flush(self):
        self._stream.flush()
        self._log_file.flush()


def main():
    parser = argparse.ArgumentParser(description="NIFTY Directional Strategy Engine")
    parser.add_argument("--mode", choices=["optimize"], default="optimize",
                        help="optimize is the only mode (kept for --mode compatibility)")
    parser.add_argument("--config", default="configs/optimization.json")
    args = parser.parse_args()
    config = load_json(args.config)

    log_dir = Path(config.get("output", {}).get("directory", "output_data"))
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"optimize_run_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

    real_stdout = sys.stdout
    with log_path.open("w", encoding="utf-8") as log_file:
        sys.stdout = _Tee(real_stdout, log_file)
        try:
            run_optimize(config, config_path=args.config)
        finally:
            sys.stdout = real_stdout

    print(f"LOG FILE: {log_path}")


if __name__ == "__main__":
    main()
