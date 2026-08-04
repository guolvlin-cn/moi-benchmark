#!/usr/bin/env python3
"""Build enron.sqlite from ~/my_data/ CSV files.

Usage: python build_sqlite.py
Output: ../data/enron.sqlite
"""
import csv
import sqlite3
import sys
from pathlib import Path

CSV_DIR = Path.home() / "my_data"
OUT_PATH = Path(__file__).resolve().parent.parent / "data" / "enron.sqlite"

CSV_TABLE_MAP = {
    "enron_email__kb_e0b57758b08421f36c23ba0e.csv": "enron_email",
    "enron_emailinfo__kb_585f52db351081f707787cd8.csv": "enron_emailinfo",
    "enron_emailorig__kb_d8ff2a19a41e0ebf77e928c7.csv": "enron_emailorig",
    "enron_emailto__kb_522ada3c2eab7f34478eb48b.csv": "enron_emailto",
    "enron_emailxto__kb_0fba35eddaaa275d563d2c70.csv": "enron_emailxto",
    "enron_source__kb_b553c9798b5c72234f52139c.csv": "enron_source",
}

DDL = {
    "enron_email": """
        CREATE TABLE enron_email (
            id INTEGER,
            people TEXT,
            mailbox TEXT,
            nnn INTEGER
        )
    """,
    "enron_emailinfo": """
        CREATE TABLE enron_emailinfo (
            id INTEGER,
            messageid TEXT,
            date TEXT,
            subject TEXT,
            \"from\" TEXT,
            \"to\" TEXT,
            xfrom TEXT,
            xto TEXT,
            body TEXT
        )
    """,
    "enron_emailorig": """
        CREATE TABLE enron_emailorig (
            id INTEGER,
            nth INTEGER,
            subject TEXT,
            \"from\" TEXT,
            \"to\" TEXT,
            xfrom TEXT,
            xto TEXT
        )
    """,
    "enron_emailto": """
        CREATE TABLE enron_emailto (
            id INTEGER,
            nthto INTEGER,
            \"to\" TEXT
        )
    """,
    "enron_emailxto": """
        CREATE TABLE enron_emailxto (
            id INTEGER,
            nthxto INTEGER,
            xto TEXT
        )
    """,
    "enron_source": """
        CREATE TABLE enron_source (
            id INTEGER,
            source_file_id TEXT,
            source_name TEXT,
            xfilename TEXT,
            xfolder TEXT,
            xorigin TEXT
        )
    """,
}

INT_COLS = {"id", "nnn", "nth", "nthto", "nthxto"}


def guess_type(col: str, val: str) -> str:
    if col in INT_COLS:
        try:
            int(val)
            return "INTEGER"
        except (ValueError, TypeError):
            return "NULL"
    return "TEXT"


def main():
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    if OUT_PATH.exists():
        OUT_PATH.unlink()

    conn = sqlite3.connect(str(OUT_PATH))
    conn.execute("PRAGMA journal_mode=OFF")
    conn.execute("PRAGMA synchronous=OFF")
    cur = conn.cursor()

    for csv_fname, table_name in CSV_TABLE_MAP.items():
        csv_path = CSV_DIR / csv_fname
        if not csv_path.exists():
            print(f"SKIP {csv_fname}: not found")
            continue

        print(f"Building {table_name}...")
        cur.execute(f"DROP TABLE IF EXISTS \"{table_name}\"")
        cur.execute(DDL[table_name])

        with open(csv_path, "r", encoding="utf-8", errors="replace") as f:
            reader = csv.DictReader(f)
            columns = reader.fieldnames
            if not columns:
                print(f"  SKIP: no columns")
                continue

            placeholders = ", ".join(["?"] * len(columns))
            col_names = ", ".join(f'"{c}"' for c in columns)
            sql = f'INSERT INTO "{table_name}" ({col_names}) VALUES ({placeholders})'

            batch = []
            count = 0
            for row in reader:
                cleaned = []
                for col in columns:
                    val = row.get(col, None)
                    if val is None or val == "":
                        if col in INT_COLS:
                            cleaned.append(None)
                        else:
                            cleaned.append("")
                    elif col in INT_COLS:
                        try:
                            cleaned.append(int(val))
                        except (ValueError, TypeError):
                            cleaned.append(None)
                    else:
                        if isinstance(val, str) and len(val) > 60000:
                            cleaned.append(val[:60000])
                        else:
                            cleaned.append(val)
                batch.append(tuple(cleaned))

                if len(batch) >= 10000:
                    cur.executemany(sql, batch)
                    count += len(batch)
                    batch = []
                    print(f"  {count} rows...", end="\r")

            if batch:
                cur.executemany(sql, batch)
                count += len(batch)

        print(f"  {table_name}: {count} rows imported")

    # Create indexes for common query patterns
    print("\nCreating indexes...")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_email_people ON enron_email(people)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_email_mailbox ON enron_email(mailbox)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_emailinfo_from ON enron_emailinfo(\"from\")")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_emailinfo_date ON enron_emailinfo(date)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_emailto_id ON enron_emailto(id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_emailxto_id ON enron_emailxto(id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_source_id ON enron_source(id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_source_xorigin ON enron_source(xorigin)")

    conn.commit()
    cur.execute("ANALYZE")
    conn.close()

    size_mb = OUT_PATH.stat().st_size / (1024 * 1024)
    print(f"\nDone: {OUT_PATH} ({size_mb:.1f} MB)")


if __name__ == "__main__":
    main()
