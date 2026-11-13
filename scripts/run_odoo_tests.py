"""Create a new disposable database and run installation, regression and smoke checks.

Run inside an Odoo container. Connection settings come from its standard
HOST, PORT, USER and PASSWORD environment variables. Existing databases are
never updated or removed by this runner.
"""

import argparse
import configparser
import os
import re
import subprocess
import tempfile
from pathlib import Path

import psycopg2
from psycopg2 import sql


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", default="CabochonCITest")
    parser.add_argument("--addons-path", type=Path, default=Path(__file__).resolve().parents[1] / "addons")
    args = parser.parse_args()
    if not re.fullmatch(r"Cabochon[A-Za-z0-9_]*Test", args.database):
        parser.error("Use a new disposable database named Cabochon*Test")
    connection = {
        "host": os.environ["HOST"], "port": os.environ.get("PORT", "5432"),
        "user": os.environ["USER"], "password": os.environ["PASSWORD"],
    }
    # CREATE DATABASE fails safely if this name already exists.
    database_connection = psycopg2.connect(dbname="postgres", **connection)
    try:
        database_connection.autocommit = True
        with database_connection.cursor() as cursor:
            cursor.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(args.database)))
    finally:
        database_connection.close()
    with tempfile.TemporaryDirectory(prefix="cabochon-tests-") as directory:
        root = Path(directory)
        config = configparser.ConfigParser(interpolation=None)
        config["options"] = {
            **{"db_" + key: str(value) for key, value in connection.items()},
            "addons_path": "/usr/lib/python3/dist-packages/odoo/addons," + str(args.addons_path),
            "data_dir": os.environ.get("ODOO_DATA_DIR", "/var/lib/odoo"), "max_cron_threads": "0",
            "http_interface": "127.0.0.1", "http_port": "8099",
        }
        config_path = root / "odoo.conf"
        with config_path.open("w", encoding="utf-8") as output:
            config.write(output)
        config_path.chmod(0o600)
        common = ["--config", str(config_path), "-d", args.database]
        log_path = root / "odoo-tests.log"
        installation = subprocess.run([
            "odoo", *common, "-i", "cabochon_base,cabochon_manufacturing",
            "--without-demo=True", "--stop-after-init", "--test-enable",
            "--test-tags", "/cabochon_manufacturing", "--logfile", str(log_path),
        ], check=False)
        log = log_path.read_text(encoding="utf-8") if log_path.exists() else ""
        summary = re.search(r"0 failed, 0 error\(s\) of ([1-9][0-9]*) tests", log)
        if installation.returncode or not summary:
            print(log)
            raise RuntimeError("Odoo did not report a successful nonempty test run")
        print(summary.group(0), flush=True)
        for script, marker in (("smoke_zero_start.py", "SMOKE_ZERO_START_OK"), ("check_concurrency.py", "CONCURRENCY_OK")):
            result = subprocess.run(
                ["odoo", "shell", *common, "--no-http"],
                input=Path(__file__).with_name(script).read_text(encoding="utf-8"),
                text=True, capture_output=True, check=False,
            )
            if result.returncode or marker not in result.stdout:
                print(result.stdout)
                print(result.stderr)
                raise RuntimeError(f"{script} failed (exit {result.returncode})")
            print(result.stdout.strip(), flush=True)
    print(f"TEST_DATABASE_RETAINED: {args.database}")


if __name__ == "__main__":
    main()
