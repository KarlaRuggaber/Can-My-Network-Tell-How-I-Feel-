"""Results frontend for "Can My Network Tell How I Feel?".

The package reads the gateway's processed Parquet partitions, computes the daily
metrics with the unchanged metric code of the thesis app (app_pcap_to_dsm5/app/metrics),
scores them with the FASL config and serves the results to the React UI.
"""
