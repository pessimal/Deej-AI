import argparse
import os

os.environ["CUDA_VISIBLE_DEVICES"] = ""


import torch
from audiodiffusion.audio_encoder import AudioEncoder
from huggingface_hub import Repository

if __name__ == "__main__":
    """
    Entry point for the pt_to_hf script.

    Converts a PyTorch MP3ToVec model to a Hugging Face MP3ToVec model.

    Args:
        --mp3tovec_model_file (str): Path to the MP3ToVec model file. Default is "models/mp3tovec.ckpt".
        --hub_model_id (str): Hugging Face model ID. Default is "teticio/audio-encoder".
        --output_dir (str): Hugging Face model path. Default is "models/audio-encoder".
        --push_to_hub (bool): Push to Hugging Face hub. Default is False.

    Returns:
        None
    """
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--mp3tovec_model_file",
        type=str,
        default="models/mp3tovec.ckpt",
        help="MP3ToVec model file",
    )
    parser.add_argument(
        "--hub_model_id",
        type=str,
        default="teticio/audio-encoder",
        help="Hugging Face model ID",
    )
    parser.add_argument(
        "--output_dir",
        type=str,
        default="models/audio-encoder",
        help="Hugging Face model path",
    )
    parser.add_argument(
        "--push_to_hub",
        type=bool,
        default=False,
        help="Push to Hugging Face hub",
    )
    args = parser.parse_args()

    audio_encoder = AudioEncoder()
    audio_encoder.eval()
    audio_encoder.load_state_dict(
        {
            k.replace("model.", ""): v
            for k, v in torch.load(
                args.mp3tovec_model_file, map_location=torch.device("cpu")
            )["state_dict"].items()
        },
    )

    if args.push_to_hub:
        repo = Repository(args.output_dir, clone_from=args.hub_model_id)
    audio_encoder.save_pretrained(args.output_dir)
    if args.push_to_hub:
        repo.push_to_hub()  # type: ignore
