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

## GitHub Actions GPU availability

Official GitHub sources:
- https://github.blog/changelog/2024-07-08-github-actions-gpu-hosted-runners-are-now-generally-available/
- https://docs.github.com/en/actions/reference/runners/larger-runners

- GitHub documents GPU larger runners with a Tesla T4, 4 vCPU, 28 GB RAM, 16 GB VRAM, and 176 GB SSD on Ubuntu/Windows.
- GPU larger runners must be configured through organization or enterprise runner groups and selected by the runner label in `runs-on`; they are not the same as the default `ubuntu-latest` runner.
- GitHub's documentation notes that larger runners require valid billing information and a positive Actions spending limit.
- The current repository owner `ahmedadelmiedo-hub` is a personal GitHub user account, the repository is public, and the repository currently has zero self-hosted runners.

## Practical implication

The current `ubuntu-latest` workflow cannot be assumed to have a GPU. The workable GitHub-only route is either to configure an eligible GitHub GPU larger runner and target its generated label, or to use an external GPU runner registered as self-hosted. A CPU-only SadTalker workflow can be used only as a diagnostic experiment; it is not a reliable production path for a long episode.

## Free GPU options

Official Google Colab FAQ: https://research.google.com/colaboratory/faq.html
- Colab offers free access to compute resources including GPUs, but resources are not guaranteed or unlimited and usage limits fluctuate.
- Colab virtual machines are deleted after idle periods and have a maximum lifetime.
- The free managed runtime restricts abuse and explicitly lists deepfakes among disallowed activities. This is a major policy risk for a talking-avatar workflow, so Colab should not be treated as an unqualified production route for Nour.

Official Kaggle GPU documentation: https://www.kaggle.com/docs/efficient-gpu-usage
- Kaggle documents free NVIDIA Tesla P100 access for notebooks, with a weekly GPU quota of 30 hours or sometimes higher depending on demand and resources.
- Kaggle advises monitoring GPU usage, stopping idle sessions, and avoiding inefficient batch sessions.
- Kaggle is a more technically suitable free-GPU test environment for SadTalker than Colab, but availability and quota are still not guaranteed; it is best for manual short/episode tests rather than unattended GitHub Actions execution.

## Updated practical recommendation

For a free GPU, use Kaggle for a manual SadTalker notebook test and keep GitHub Actions for source control, artifact storage, and later publishing. Do not route the talking-avatar generation through a free Colab managed runtime without checking current policy because the official FAQ lists deepfakes as disallowed. GitHub's standard public-repository runner remains CPU-only; GitHub GPU larger runners require separate runner configuration and billing eligibility.

Official Kaggle Acceptable Use Policy: https://www.kaggle.com/aup
- Kaggle prohibits resource abuse and activities unrelated to ML/data science, but the policy page reviewed does not include the same explicit blanket ban on deepfake generation that appears in the Colab FAQ.
- Any use must still comply with Kaggle's legal, intellectual-property, privacy, and deceptive-content rules. The Nour asset is a fictional cartoon character, which reduces identity/privacy risk, but the channel should disclose synthetic/AI-generated production where appropriate.
- Kaggle remains a manual notebook route, not a native GitHub Actions runner. A GitHub-to-Kaggle unattended bridge would require Kaggle credentials and must respect Kaggle's session/quota policies.
