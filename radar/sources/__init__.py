"""Job sources. Each module exposes fetch(cfg, fetcher) -> list[Job]."""
from . import euraxess, greenhouse, linkedin

SOURCES = {
    "linkedin": linkedin,
    "euraxess": euraxess,
    "greenhouse": greenhouse,
}
