"""Job sources: name -> fetch(cfg, fetcher) -> list[Job]. The name is also the config key under `search:`."""
from . import ats, euraxess, greenhouse, linkedin, portals, smartrecruiters

SOURCES = {
    "linkedin": linkedin.fetch,
    "euraxess": euraxess.fetch,
    "greenhouse": greenhouse.fetch,
    "smartrecruiters": smartrecruiters.fetch,
    "workday": ats.fetch_workday,
    "lever": ats.fetch_lever,
    "ashby": ats.fetch_ashby,
    "hrpeak": portals.fetch_hrpeak,
    "baykar": portals.fetch_baykar,
}
