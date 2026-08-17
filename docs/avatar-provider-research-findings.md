# Avatar provider research findings

## MuseTalk
Source: https://github.com/TMElyralab/MuseTalk

- MuseTalk is an audio-driven lip-sync model that modifies an unseen face from input audio.
- The official repository says it supports multiple languages and reports 30fps+ real-time inference on an NVIDIA Tesla V100.
- The repository recommends Python 3.10, CUDA 11.7/11.8, PyTorch 2.0.1, FFmpeg, and MMLab dependencies.
- It expects an input video/face region, not only a still image; the recommended architecture is to create a base talking-head video first, then apply lip sync.

## Wav2Lip
Source: https://github.com/Rudrabha/Wav2Lip

- The project provides open-source code and pretrained weights for syncing an input video to target audio, including CGI and synthetic voices.
- Its open-source model is explicitly restricted to research/academic/personal use because of the LRS2-trained weights; commercial use is prohibited in the repository disclaimer.
- It requires Python, FFmpeg, face-detection weights, and a GPU is strongly preferable.
- The repository also presents a separate commercial Sync API; that API is not a free/open-source replacement.

## Preliminary conclusion

For this project, MuseTalk is the stronger open-source candidate if the user can provide a CUDA GPU and a short base video of Nour. Wav2Lip is a lighter fallback for personal/non-commercial testing, but its open-source license restrictions make it unsuitable for a monetized YouTube channel without a separate license. A local open-source route is not zero-infrastructure: it needs persistent storage, model weights, a compatible Python/CUDA environment, and a GPU; the current GitHub-hosted runner and sandbox do not provide that GPU path.

## SadTalker
Source: https://github.com/OpenTalker/SadTalker

- SadTalker directly accepts a single portrait image plus audio and outputs a talking-head video.
- The official README states that the project license was updated to Apache 2.0 and the previous non-commercial restriction was removed.
- It supports head pose and expression motion, plus still/full-body modes, and provides a CLI using `--driven_audio` and `--source_image`.
- The official installation instructions target Python 3.8, PyTorch 1.12.1/CUDA 11.3, FFmpeg, downloaded checkpoints, and optional GFPGAN enhancement.
- It is a better shape match for Nour than Wav2Lip because it can start from a still character portrait; it still needs a CUDA-capable machine for practical batch production.

## Updated recommendation

SadTalker is the most direct open-source replacement for D-ID for this repository: `image + segment audio -> talking-head MP4`. MuseTalk is a strong lip-sync backend when a base video exists and can be useful later for higher-quality mouth synchronization. Wav2Lip remains a personal/non-commercial fallback because the official open-source README prohibits commercial use of its released model.
