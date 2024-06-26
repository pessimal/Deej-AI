# import debugpy
# debugpy.listen(5678)

import argparse
import concurrent.futures
import gc
import json
import os
import traceback
from time import sleep
from typing import Dict, Optional

import requests
from tqdm import tqdm
from utils import (
    get_access_token,
    paginate,
    read_playlists,
    read_tracks,
    request_with_proxy,
    write_playlists,
    write_tracks,
)

MARKET = "GB"  # UK
access_token = None


def get_playlist_items(
    playlist_id: str, limit: int = 50, offset: int = 0, proxy: Optional[str] = None
) -> Dict:
    """
    Retrieves the items (tracks) in a Spotify playlist and associated information.

    Args:
        playlist_id (str): The ID of the playlist to retrieve items for.
        limit (int): The maximum number of items to retrieve. Default is 50.
        offset (int): The offset to start retrieving items from. Default is 0.
        proxy (str): The name of the proxy Lambda function to use for the request (see README). Default is None.

    Returns:
        A dictionary containing the items in the playlist and associated information.
    """
    global access_token
    for _ in range(0, 2):
        try:
            if access_token is None:
                access_token = get_access_token(proxy=proxy)
            url = f"https://api.spotify.com/v1/playlists/{playlist_id}/tracks?limit={limit}&offset={offset}&market={MARKET}"
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            }
            items = (
                requests.get(url=url, headers=headers).json()
                if proxy is None
                else json.loads(
                    request_with_proxy("GET", url=url, headers=headers, proxy=proxy)
                )
            )
            if "error" not in items:
                return items
            print(items["error"])
        except:
            traceback.print_exc()
            pass
        sleep(1)
        access_token = get_access_token(proxy=proxy)
    print(f"Skipping {playlist_id}")
    return {}


def main() -> None:
    """
    Entry point for the get_tracks script.

    Retrieves tracks for a list of Spotify playlists.

    Args:
        --batch_size (int): The number of tracks to retrieve per batch. Default is 10000.
        --max_workers (int): The maximum number of cores to use. Default is 32.
        --playlists_file (str): Path to the input playlist CSV file. Default is "data/playlists.csv".
        --playlist_details_file (str): Path to the output playlist details CSV file. Default is "data/playlists.csv".
        --tracks_file (str): Path to the output CSV file to save track information. Default is "data/tracks.csv".

    Returns:
        None
    """
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--batch_size",
        type=int,
        default=10000,
        help="Batch size",
    )
    parser.add_argument(
        "--max_workers",
        type=int,
        default=32,
        help="Maximum number of cores to use",
    )
    parser.add_argument(
        "--playlists_file",
        type=str,
        default="data/playlists.csv",
        help="Playlists CSV file",
    )
    parser.add_argument(
        "--playlist_details_file",
        type=str,
        default="data/playlist_details.csv",
        help="Playlist details CSV file",
    )
    parser.add_argument(
        "--proxy",
        type=str,
        default=None,
        help="Proxy lambda function (see https://github.com/teticio/lambda-scraper)",
    )
    parser.add_argument(
        "--tracks_file",
        type=str,
        default="data/tracks.csv",
        help="Tracks CSV file",
    )
    args = parser.parse_args()

    playlists = read_playlists(args.playlists_file)
    start_index = len(playlists)
    keys = list(playlists.keys())
    while start_index > 0 and len(playlists[keys[start_index - 1]]) == 0:
        start_index -= 1
    tracks = read_tracks(args.tracks_file) if os.path.exists(args.tracks_file) else {}

    for i in range(start_index, len(playlists), args.batch_size):
        print(f"{i}/{len(playlists)}")
        batch = keys[i : i + args.batch_size]

        with concurrent.futures.ProcessPoolExecutor(
            max_workers=args.max_workers
        ) as executor:
            futures = {
                executor.submit(
                    paginate,
                    get_playlist_items,
                    delay=0.1,
                    playlist_id=playlist_id,
                    proxy=f"{args.proxy}-{i % args.max_workers}"
                    if args.proxy
                    else None,
                ): playlist_id
                for i, playlist_id in enumerate(tqdm(batch, desc="Setting up jobs"))
            }
            for i, future in enumerate(
                tqdm(
                    concurrent.futures.as_completed(futures),
                    total=len(futures),
                    desc="Getting playlist items",
                )
            ):
                playlist_id = futures[future]
                items = future.result()
                del futures[future]

                for item in items:
                    if item["track"] is None or item["track"]["id"] is None:
                        continue
                    if item["track"]["id"] in tracks:
                        tracks[item["track"]["id"]]["count"] = (
                            int(tracks[item["track"]["id"]]["count"]) + 1
                        )
                    else:
                        tracks[item["track"]["id"]] = {
                            "artist": item["track"]["artists"][0]["name"],
                            "title": item["track"]["name"],
                            "url": item["track"]["preview_url"]
                            if item["track"]["preview_url"] is not None
                            else "",
                            "count": 1,
                        }
                    playlists[playlist_id].append(item["track"]["id"])
                del items

        write_tracks(tracks, args.tracks_file)
        write_playlists(playlists, args.playlist_details_file)
        gc.collect()


if __name__ == "__main__":
    main()
