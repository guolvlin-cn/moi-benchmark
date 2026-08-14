#!/usr/bin/env python3
"""把冻结的 Spider Mix50 CSV 生成可在 MOI/MatrixOne 执行的 INSERT SQL。"""

from __future__ import annotations

import csv
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CSV_ROOT = ROOT / "database" / "csv"
OUTPUT = ROOT / "database" / "data" / "moi_matrixone_data.sql"

TABLES = [
    ("pets_1", "Student", ["StuID", "LName", "Fname", "Age", "Sex", "Major", "Advisor", "city_code"]),
    ("pets_1", "Pets", ["PetID", "PetType", "pet_age", "weight"]),
    ("pets_1", "Has_Pet", ["StuID", "PetID"]),
    ("concert_singer", "stadium", ["Stadium_ID", "Location", "Name", "Capacity", "Highest", "Lowest", "Average"]),
    ("concert_singer", "singer", ["Singer_ID", "Name", "Country", "Song_Name", "Song_release_year", "Age", "Is_male"]),
    ("concert_singer", "concert", ["concert_ID", "concert_Name", "Theme", "Stadium_ID", "Year"]),
    ("concert_singer", "singer_in_concert", ["concert_ID", "Singer_ID"]),
    ("car_1", "continents", ["ContId", "Continent"]),
    ("car_1", "countries", ["CountryId", "CountryName", "Continent"]),
    ("car_1", "car_makers", ["Id", "Maker", "FullName", "Country"]),
    ("car_1", "model_list", ["ModelId", "Maker", "Model"]),
    ("car_1", "car_names", ["MakeId", "Model", "Make"]),
    ("car_1", "cars_data", ["Id", "MPG", "Cylinders", "Edispl", "Horsepower", "Weight", "Accelerate", "Year"]),
]

NUMERIC_COLUMNS = {
    "StuID", "Age", "Major", "Advisor", "PetID", "pet_age", "weight",
    "Stadium_ID", "Capacity", "Highest", "Lowest", "Average", "Singer_ID",
    "Song_release_year", "concert_ID", "Year", "ContId", "CountryId",
    "Continent", "Id", "Country", "ModelId", "Maker", "MakeId", "MPG",
    "Cylinders", "Edispl", "Horsepower", "Weight", "Accelerate",
}


def sql_value(column: str, value: str) -> str:
    if value.strip().lower() == "null":
        return "NULL"
    if column in NUMERIC_COLUMNS and re.fullmatch(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)", value.strip()):
        return value.strip()
    return "'" + value.replace("\\", "\\\\").replace("'", "''") + "'"


def main() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "-- Spider Mix50 冻结数据：供 MOI / MatrixOne SQL 编辑器执行。",
        "-- 只插入数据，不清空已有表；请在空表上执行一次。",
        "",
    ]

    for database, table, expected_columns in TABLES:
        csv_path = CSV_ROOT / database / f"{table}.csv"
        with csv_path.open(newline="", encoding="utf-8-sig") as source:
            reader = csv.DictReader(source)
            if reader.fieldnames != expected_columns:
                raise ValueError(
                    f"{csv_path}: columns {reader.fieldnames!r} != {expected_columns!r}"
                )
            rows = list(reader)

        columns_sql = ", ".join(f"`{column}`" for column in expected_columns)
        values_sql = []
        for row in rows:
            values_sql.append(
                "(" + ", ".join(sql_value(column, row[column]) for column in expected_columns) + ")"
            )

        lines.extend(
            [
                f"INSERT IGNORE INTO `{database}`.`{table}` ({columns_sql}) VALUES",
                ",\n".join(values_sql) + ";",
                "",
            ]
        )

    lines.extend(
        [
            "-- 导入完成后核对行数。",
            *[
                f"SELECT '{database}.{table}' AS table_name, COUNT(*) AS row_count FROM `{database}`.`{table}`;"
                for database, table, _ in TABLES
            ],
            "",
        ]
    )
    OUTPUT.write_text("\n".join(lines), encoding="utf-8")
    print(OUTPUT)


if __name__ == "__main__":
    main()
