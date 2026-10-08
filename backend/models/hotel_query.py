"""Immutable contract for the narrowly scoped, untrusted hotel SQL proposal."""

import math
from dataclasses import dataclass

MAX_HOTEL_QUERY_LENGTH = 8000
MAX_HOTEL_QUERY_ROWS = 100
MAX_HOTEL_RESULT_CHARACTERS = 32000
HotelQueryValue = str | int | float | None


@dataclass(frozen=True)
class HotelQuery:
    sql: str

    def __post_init__(self) -> None:
        if (
            not isinstance(self.sql, str)
            or not self.sql.strip()
            or len(self.sql) > MAX_HOTEL_QUERY_LENGTH
            or "\x00" in self.sql
        ):
            raise ValueError("A bounded, non-empty hotel query is required.")
        object.__setattr__(self, "sql", self.sql.strip())

    @property
    def limited_sql(self) -> str:
        # One extra row detects truncation. SQLite validates this entire statement;
        # the newline prevents a trailing line comment from hiding the wrapper.
        sql = self.sql.removesuffix(";").rstrip()
        return f"SELECT * FROM (\n{sql}\n) AS hotel_records LIMIT {MAX_HOTEL_QUERY_ROWS + 1}"


@dataclass(frozen=True)
class HotelQueryResult:
    columns: tuple[str, ...]
    rows: tuple[tuple[HotelQueryValue, ...], ...]
    truncated: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.columns, tuple) or not all(
            isinstance(column, str) for column in self.columns
        ):
            raise ValueError("Query columns must be immutable text.")
        if not isinstance(self.rows, tuple) or len(self.rows) > MAX_HOTEL_QUERY_ROWS:
            raise ValueError("Query rows exceed the result limit.")
        for row in self.rows:
            if not isinstance(row, tuple) or len(row) != len(self.columns):
                raise ValueError("Query rows must match their columns.")
            for value in row:
                if value is not None and type(value) not in (str, int, float):
                    raise ValueError("Query values must be JSON scalar values.")
                if type(value) is float and not math.isfinite(value):
                    raise ValueError("Query numbers must be finite.")
