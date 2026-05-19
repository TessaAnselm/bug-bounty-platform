from temporalio import activity


@activity.defn
async def fingerprint_tech(probe_results: list[dict]) -> list[dict]:
    """Extract and normalize technology data already in httpx probe results."""
    tech_map = []
    for r in probe_results:
        techs = r.get("technologies", [])
        if techs:
            tech_map.append({"url": r.get("url", ""), "technologies": techs})
    return tech_map
