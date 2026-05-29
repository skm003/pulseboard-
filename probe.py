"""One-off validation: scrape a FEW items per platform (cheap) and dump raw
fields so we can confirm collectors.py maps them correctly."""
import json
from clients import get_apify, run_dataset_id
from config import IG_ACTOR, YT_ACTOR


def dump(title, items, outfile):
    print(f"\n=== {title} ===")
    if not items:
        print("(no items returned)")
        return
    print("COUNT:", len(items))
    print("RAW KEYS:", sorted(items[0].keys()))
    with open(outfile, "w", encoding="utf-8") as f:
        json.dump(items, f, indent=2, default=str)
    print("saved ->", outfile)


def probe_ig(username="natgeo"):
    client = get_apify()
    run = client.actor(IG_ACTOR).call(run_input={
        "directUrls": [f"https://www.instagram.com/{username}/"],
        "resultsType": "posts", "resultsLimit": 3, "addParentData": False,
    })
    dump(f"INSTAGRAM {IG_ACTOR} : {username}",
         list(client.dataset(run_dataset_id(run)).iterate_items()), "probe_ig.json")


def probe_yt(url="https://www.youtube.com/@mkbhd"):
    client = get_apify()
    run = client.actor(YT_ACTOR).call(run_input={
        "startUrls": [{"url": url}], "maxResults": 3, "sortVideosBy": "NEWEST",
    })
    dump(f"YOUTUBE {YT_ACTOR} : {url}",
         list(client.dataset(run_dataset_id(run)).iterate_items()), "probe_yt.json")


if __name__ == "__main__":
    import sys
    which = sys.argv[1] if len(sys.argv) > 1 else "both"
    if which in ("ig", "both"):
        probe_ig()
    if which in ("yt", "both"):
        probe_yt()
