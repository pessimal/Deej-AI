import argparse
import os

os.environ["CUDA_VISIBLE_DEVICES"] = ""

import numpy as np
import torch
from audiodiffusion.audio_encoder import AudioEncoder
from keras.models import load_model, save_model
from tensorflow.compat.v1.keras.losses import cosine_proximity  # type: ignore
from tensorflow.keras.layers import Dropout  # type: ignore
from tensorflow.keras.layers import (  # type: ignore
    BatchNormalization,
    Dense,
    Flatten,
    Input,
    LeakyReLU,
    MaxPooling2D,
    SeparableConv2D,
)
from tensorflow.keras.models import Sequential  # type: ignore

if __name__ == "__main__":
    """
    Entry point for the pt_to_tf script.

    Converts a PyTorch MP3ToVec model to a TensorFlow MP3ToVec model.

    Args:
        --pt_model_file (str): Path to the PyTorch model file. Default is "models/mp3tovec.ckpt".
        --tf_model_file (str): Path to the TensorFlow model file. Default is "models/speccymodel".

    Returns:
        None
    """
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--pt_model_file",
        type=str,
        default="models/mp3tovec.ckpt",
        help="PyTorch model path",
    )
    parser.add_argument(
        "--tf_model_file",
        type=str,
        default="models/speccy_model",
        help="TensorFlow model path",
    )
    args = parser.parse_args()

    pytorch_model = AudioEncoder()
    pytorch_model.eval()
    pytorch_model.load_state_dict(
        {
            k.replace("model.", ""): v
            for k, v in torch.load(
                args.pt_model_file, map_location=torch.device("cpu")
            )["state_dict"].items()
        },
    )

    input_shape = (96, 216, 1)
    model_input = Input(shape=input_shape, name="input")

    model = Sequential(
        [
            Input(shape=input_shape, name="input"),
            SeparableConv2D(
                32,
                3,
                padding="same",
                activation=LeakyReLU(0.2),
                name=f"separable_conv2d_1",
            ),
            BatchNormalization(name=f"batch_normalization_1"),
            MaxPooling2D((2, 2)),
            Dropout(rate=0.2),
            SeparableConv2D(
                64,
                3,
                padding="same",
                activation=LeakyReLU(0.2),
                name=f"separable_conv2d_2",
            ),
            BatchNormalization(name=f"batch_normalization_2"),
            MaxPooling2D((2, 2)),
            Dropout(rate=0.3),
            SeparableConv2D(
                128,
                3,
                padding="same",
                activation=LeakyReLU(0.2),
                name=f"separable_conv2d_3",
            ),
            BatchNormalization(name=f"batch_normalization_3"),
            MaxPooling2D((2, 2)),
            Dropout(rate=0.4),
            Flatten(),
            Dense(1024, activation=LeakyReLU(0.2), name="dense_1"),
            BatchNormalization(name=f"batch_normalization_4"),
            Dropout(rate=0.5),
            Dense(100, name="dense_2"),
        ]
    )

    for conv_block in range(3):
        model.get_layer(name=f"separable_conv2d_{conv_block+1}").set_weights(
            [
                np.transpose(
                    pytorch_model.state_dict()[
                        f"conv_blocks.{conv_block}.sep_conv.depthwise.weight"
                    ]
                    .float()
                    .numpy(),
                    (2, 3, 0, 1),
                ),
                np.transpose(
                    pytorch_model.state_dict()[
                        f"conv_blocks.{conv_block}.sep_conv.pointwise.weight"
                    ]
                    .float()
                    .numpy(),
                    (2, 3, 1, 0),
                ),
                pytorch_model.state_dict()[
                    f"conv_blocks.{conv_block}.sep_conv.pointwise.bias"
                ]
                .float()
                .numpy(),
            ]
        )
        model.get_layer(name=f"batch_normalization_{conv_block+1}").set_weights(
            [
                pytorch_model.state_dict()[
                    f"conv_blocks.{conv_block}.batch_norm.weight"
                ]
                .float()
                .numpy(),
                pytorch_model.state_dict()[f"conv_blocks.{conv_block}.batch_norm.bias"]
                .float()
                .numpy(),
                pytorch_model.state_dict()[
                    f"conv_blocks.{conv_block}.batch_norm.running_mean"
                ]
                .float()
                .numpy(),
                pytorch_model.state_dict()[
                    f"conv_blocks.{conv_block}.batch_norm.running_var"
                ]
                .float()
                .numpy(),
            ]
        )

    model.get_layer(name=f"batch_normalization_{conv_block+2}").set_weights(  # type: ignore
        [
            pytorch_model.state_dict()[f"dense_block.batch_norm.weight"]
            .float()
            .numpy(),
            pytorch_model.state_dict()[f"dense_block.batch_norm.bias"].float().numpy(),
            pytorch_model.state_dict()[f"dense_block.batch_norm.running_mean"]
            .float()
            .numpy(),
            pytorch_model.state_dict()[f"dense_block.batch_norm.running_var"]
            .float()
            .numpy(),
        ]
    )

    model.get_layer(name=f"dense_1").set_weights(
        [
            np.transpose(
                pytorch_model.state_dict()[f"dense_block.dense.weight"].float().numpy(),
                (1, 0),
            ),
            pytorch_model.state_dict()[f"dense_block.dense.bias"].float().numpy(),
        ]
    )
    model.get_layer(name=f"dense_2").set_weights(
        [
            np.transpose(
                pytorch_model.state_dict()[f"embedding.weight"].float().numpy(), (1, 0)
            ),
            pytorch_model.state_dict()[f"embedding.bias"].float().numpy(),
        ]
    )

    model.compile(loss=cosine_proximity, optimizer="adam")
    save_model(model=model, filepath=args.tf_model_file, save_format="h5")
    model = load_model(args.tf_model_file)
    if model is None:
        raise ValueError("Failed to load model")

    # test
    np.random.seed(42)
    example = np.random.random_sample((1, 96, 216, 1)).astype(np.float32)
    with torch.no_grad():
        assert (
            np.abs(
                model.predict(example)
                - pytorch_model(torch.from_numpy(example).permute(0, 3, 1, 2)).numpy()
            ).max()
            < 2e-3
        )
