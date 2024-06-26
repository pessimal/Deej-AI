import argparse
import csv
import os
import pickle

import gensim
import pandas as pd
import yaml
from gensim.models.callbacks import CallbackAny2Vec

# for really long playlists!
csv.field_size_limit(1000000)


class Logger(CallbackAny2Vec):
    """
    Callback to log most similar tracks to test tracks during training.

    Args:
        config (dict): Config dictionary
        args (argparse.Namespace): Command-line arguments
    """

    def __init__(self, config: dict, args: argparse.Namespace) -> None:
        self.config = config
        self.args = args
        self.epoch = 0
        self.loss = 0
        self.tracks = (
            pd.read_csv(
                args.tracks_file,
                header=None,
                index_col=0,
                names=["artist", "title", "url", "count"],
            )
            .fillna("")
            .to_dict(orient="index")
        )

    def on_epoch_end(self, model: gensim.models.Word2Vec) -> None:
        """
        Log most similar tracks to test tracks at the end of each epoch.

        Args:
            model (gensim.models.Word2Vec): The Track2Vec model

        Returns:
            None
        """
        self.epoch += 1
        print(
            f"Epoch {self.epoch} loss = {(model.get_latest_training_loss() - self.loss) / self.config['model']['batch_words']}"
        )
        self.loss = model.get_latest_training_loss()
        model.save(self.args.track2vec_model_file)
        # inference doesn't work properly unless we load the model from disk
        model = gensim.models.Word2Vec.load(self.args.track2vec_model_file)
        for track_id in self.config["data"]["test_track_ids"]:
            print(
                f"\u001b]8;;{self.tracks[track_id]['url']}\u001b\\{self.tracks[track_id]['artist']} - {self.tracks[track_id]['title']}\u001b]8;;\u001b\\"
            )  # type: ignore
            most_similar = model.wv.most_similar(positive=[track_id], topn=8)
            for i, similar in enumerate(most_similar):
                print(
                    f"{i + 1}. \u001b]8;;{self.tracks[similar[0]]['url']}\u001b\\{self.tracks[similar[0]]['artist']} - {self.tracks[similar[0]]['title']}\u001b]8;;\u001b\\ ({similar[1]:.2f})"
                )
            print()


if __name__ == "__main__":
    """
    Entry point for the train_track2vec script.

    Trains the Track2Vec model.

    Args:
        --config_file (str): Path to the model configuation file. Default is "config/track2vec.yaml".
        --playlists_file (str): Path to the deduplicated playlists CSV file. Default is "data/playlists_dedup.csv".
        --tracks_file (str): Path to the deduplicated tracks CSV file. Default is "data/tracks_dedup.csv".
        --max_workers (int): Maximum number of cores to use. Default is the number of cores on the machine.
        --track2vec_model_file (str): Path to the model save file without extension. Default is "models/track2vec".

    Returns:
        None
    """
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config_file",
        type=str,
        default="config/track2vec.yaml",
        help="Model configuation file",
    )
    parser.add_argument(
        "--playlists_file",
        type=str,
        default="data/playlists_dedup.csv",
        help="Deduplicated playlists CSV file",
    )
    parser.add_argument(
        "--tracks_file",
        type=str,
        default="data/tracks_dedup.csv",
        help="Deduplicated tracks CSV file",
    )
    parser.add_argument(
        "--max_workers",
        type=int,
        default=os.cpu_count() if os.cpu_count() is not None else 1,
        help="Maximum number of cores to use",
    )
    parser.add_argument(
        "--track2vec_model_file",
        type=str,
        default="models/track2vec",
        help="Model save file without extension",
    )
    args = parser.parse_args()

    with open(args.config_file, "r") as stream:
        config = yaml.safe_load(stream)

    with open(args.playlists_file, "r") as csvfile:
        reader = csv.reader(csvfile)
        playlists = [row[1:] for row in reader]

    logger = Logger(config, args)
    model = gensim.models.Word2Vec(
        sentences=playlists,
        compute_loss=True,
        min_count=1,
        workers=args.max_workers,
        callbacks=[logger],
        **config["model"],
    )

    for track in logger.tracks:
        logger.tracks[track] = model.wv[track]
    pickle.dump(logger.tracks, open(f"{args.track2vec_model_file}.p", "wb"))
