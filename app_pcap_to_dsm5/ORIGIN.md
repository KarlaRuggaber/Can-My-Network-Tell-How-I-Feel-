# Origin of this folder

This folder contains the analysis app of the Master thesis

> Nef, S. (2025). *At the Edge of Empathy: Mental-Health Awareness Through Home-Router Network Traffic Insights.* Master's thesis, University of St. Gallen.
> Nef, S., & Rodrigues, B. (2025). *CareNet: Linking Home-router Network Traffic to DSM-5 Depressive Behavior Indicators.* arXiv:2511.12772. IEEE/IFIP NOMS 2026.

| | |
| --- | --- |
| Author | Stephan Nef |
| Source | https://github.com/nefste/app_pcap_to_dsm5_public |
| Upstream commit | `12f44bc0` ("final pdf", 2025-11-01), branch `main` |
| Imported | 2026-10-16, with permission |
| License | The upstream repository has no license file. All rights remain with the author; it is included here for this bachelor project only |

## What was imported

The first commit that adds this folder ("Import app_pcap_to_dsm5 from upstream 12f44bc0") is the upstream code **unchanged**, except that these files were left out:

| Left out | Why |
| --- | --- |
| `app/processed_parquet/` (≈490 MB) | Thesis datasets. Not needed for our pipeline; available in the upstream repository |
| `app/feature_cache/` | Cached daily metrics of those datasets |
| `app/user_profiles.json` | Personal profile of the author. The app recreates the file (empty) on first start and rewrites it at runtime |
| Git history | Available in the upstream repository |

## What we changed

All later commits that touch this folder are our changes. To see them as one diff against the thesis version:

```bash
git diff <import commit> HEAD -- app_pcap_to_dsm5/
```

Overview: live ingest service (`ingest/`), shared PCAP parser (`app/utils/pcap_etl.py`), detection of growing datasets in pages 01/02 (`app/utils/partitions.py`), background filter, gateway Docker override, hostnames for inbound packets, broadcaster VOD hosts counted as their service (`SERVICE_HOSTS`, an extension of the thesis lists), productivity hits only from tool hosts on shared domains (`PRODUCTIVITY_SHARED_HOSTS`, a correction of the thesis list that changes thesis values), machine background dropped before all features (`BACKGROUND_HOST_PATTERNS`, changes UniqueSLD in thesis datasets), hostnames from the latest DNS answer the client received before the packet (`_timed_hosts`, changes F1_DistinctSocial in thesis datasets). Details: [`process/Deployment.md`](../process/Deployment.md).
