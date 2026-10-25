"""FIXED. Data, vocabulary, time budget and evaluation for the tiny-Shakespeare task.

The research agent may NOT edit this file (the harness hashes it around every run and undoes any
change) and may only use the names listed under [guard.module_allowlist] in task.toml.

Splits are contiguous: 80% train, 10% validation, 10% held-out test. The validation score
(SCORE) drives keep-or-revert. The test score (TEST) is logged but never shown to the proposer,
so over-fitting to validation shows up as a gap between the two.
"""
import math
import os
import urllib.request
from pathlib import Path

import torch
import torch.nn.functional as F

TIME_BUDGET_SECONDS = float(os.environ.get("AUTORESEARCH_BUDGET", "90"))
EVAL_BLOCK = 256       # every model is scored on windows of exactly this many characters
EVAL_WINDOWS = 400     # fixed, evenly spaced windows per split: the score is deterministic
DATA_URL = "https://raw.githubusercontent.com/karpathy/char-rnn/master/data/tinyshakespeare/input.txt"
DATA_PATH = Path(__file__).parent / "data" / "input.txt"


def _load():
    if not DATA_PATH.exists():
        DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(DATA_URL, DATA_PATH)
    text = DATA_PATH.read_text(encoding="utf-8")
    chars = sorted(set(text))
    stoi = {c: i for i, c in enumerate(chars)}
    data = torch.tensor([stoi[c] for c in text], dtype=torch.long)
    a, b = int(0.8 * len(data)), int(0.9 * len(data))
    return data[:a], data[a:b], data[b:], len(chars)


_TRAIN, _VAL, _TEST, VOCAB_SIZE = _load()


def get_batch(batch_size, block_size, device):
    """Random training windows only. There is deliberately no way to request val/test data."""
    starts = torch.randint(0, len(_TRAIN) - block_size - 1, (batch_size,))
    x = torch.stack([_TRAIN[s:s + block_size] for s in starts])
    y = torch.stack([_TRAIN[s + 1:s + block_size + 1] for s in starts])
    return x.to(device), y.to(device)


@torch.no_grad()
def _bits_per_char(model, data, device):
    starts = torch.linspace(0, len(data) - EVAL_BLOCK - 2, EVAL_WINDOWS).long()
    total, count = 0.0, 0
    for i in range(0, EVAL_WINDOWS, 100):
        chunk = starts[i:i + 100]
        x = torch.stack([data[s:s + EVAL_BLOCK] for s in chunk]).to(device)
        y = torch.stack([data[s + 1:s + EVAL_BLOCK + 1] for s in chunk]).to(device)
        out = model(x)
        logits = out[0] if isinstance(out, tuple) else out
        total += F.cross_entropy(logits.float().reshape(-1, logits.size(-1)), y.reshape(-1),
                                 reduction="sum").item()
        count += y.numel()
    return total / count / math.log(2)


def evaluate(model):
    """Score a model on validation (drives the loop) and held-out test (logged only).

    The model must map a LongTensor [B, T] to logits [B, T, VOCAB_SIZE] (or a tuple whose first
    element is those logits) for T = EVAL_BLOCK.
    """
    device = next(model.parameters()).device
    was_training = model.training
    model.eval()
    val = _bits_per_char(model, _VAL, device)
    test = _bits_per_char(model, _TEST, device)
    model.train(was_training)
    print(f"SCORE: {val:.6f}")
    print(f"TEST: {test:.6f}")
    return val
