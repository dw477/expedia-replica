"""Immutable search history and normalized query contracts."""

from dataclasses import dataclass


def normalize_query(query: str) -> str:
    """Ignore case and collapse runs of whitespace, including tabs/newlines."""
    return " ".join(query.split()).casefold()


@dataclass(frozen=True)
class SearchHistory:
    search_id: str
    user_id: str
    search_query: str
    searched_at: int

    def __post_init__(self) -> None:
        for value in (self.search_id, self.user_id, self.search_query):
            if not isinstance(value, str) or not value or value != value.strip():
                raise ValueError("Search IDs and query must be non-empty trimmed text")
        if self.search_query != normalize_query(self.search_query):
            raise ValueError("search_query must be normalized")
        if type(self.searched_at) is not int or self.searched_at < 0:
            raise ValueError("searched_at must be a non-negative Unix timestamp")


@dataclass(frozen=True)
class SearchQueryCount:
    search_query: str
    search_count: int
