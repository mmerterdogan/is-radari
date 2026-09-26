"""Job sources. Each module exposes fetch(cfg, fetcher) -> list[Job]."""
from . import euraxess, greenhouse, linkedin, smartrecruiters

SOURCES = {
    "linkedin": linkedin,
    "euraxess": euraxess,
    "greenhouse": greenhouse,
    "smartrecruiters": smartrecruiters,
}
