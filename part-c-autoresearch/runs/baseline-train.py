"""Baseline: a small character-level GPT. This is the ONLY file the research agent edits.

It trains for a fixed wall-clock budget, then hands the model to prepare.evaluate(), which
reports the validation score. Anything in this file may change (architecture, optimizer,
schedule, batch size, ...) as long as the model still maps [B, T] token ids to
[B, T, VOCAB_SIZE] logits and prepare.evaluate(model) is called once at the end.
"""
import math
import time

import torch
import torch.nn as nn
import torch.nn.functional as F

import prepare

N_LAYER = 4
N_HEAD = 4
N_EMBD = 128
BLOCK_SIZE = 256
BATCH_SIZE = 64
LEARNING_RATE = 3e-3
WEIGHT_DECAY = 0.1
WARMUP_STEPS = 100
GRAD_CLIP = 1.0
SEED = 1337


class Block(nn.Module):
    def __init__(self):
        super().__init__()
        self.ln1 = nn.LayerNorm(N_EMBD)
        self.qkv = nn.Linear(N_EMBD, 3 * N_EMBD)
        self.proj = nn.Linear(N_EMBD, N_EMBD)
        self.ln2 = nn.LayerNorm(N_EMBD)
        self.fc = nn.Linear(N_EMBD, 4 * N_EMBD)
        self.out = nn.Linear(4 * N_EMBD, N_EMBD)

    def forward(self, x):
        B, T, C = x.shape
        q, k, v = self.qkv(self.ln1(x)).split(C, dim=2)
        q, k, v = (t.view(B, T, N_HEAD, C // N_HEAD).transpose(1, 2) for t in (q, k, v))
        att = F.scaled_dot_product_attention(q, k, v, is_causal=True)
        x = x + self.proj(att.transpose(1, 2).reshape(B, T, C))
        return x + self.out(F.gelu(self.fc(self.ln2(x))))


class GPT(nn.Module):
    def __init__(self):
        super().__init__()
        self.tok = nn.Embedding(prepare.VOCAB_SIZE, N_EMBD)
        self.pos = nn.Embedding(BLOCK_SIZE, N_EMBD)
        self.blocks = nn.Sequential(*[Block() for _ in range(N_LAYER)])
        self.ln_f = nn.LayerNorm(N_EMBD)
        self.head = nn.Linear(N_EMBD, prepare.VOCAB_SIZE, bias=False)
        self.head.weight = self.tok.weight  # weight tying
        self.apply(self._init)

    @staticmethod
    def _init(m):
        if isinstance(m, (nn.Linear, nn.Embedding)):
            nn.init.normal_(m.weight, mean=0.0, std=0.02)
        if isinstance(m, nn.Linear) and m.bias is not None:
            nn.init.zeros_(m.bias)

    def forward(self, idx):
        T = idx.size(1)
        x = self.tok(idx) + self.pos(torch.arange(T, device=idx.device))
        return self.head(self.ln_f(self.blocks(x)))


def lr_at(step, progress):
    """Linear warmup, then cosine decay over the fraction of the time budget used."""
    if step < WARMUP_STEPS:
        return LEARNING_RATE * (step + 1) / WARMUP_STEPS
    return LEARNING_RATE * (0.05 + 0.95 * 0.5 * (1 + math.cos(math.pi * min(progress, 1.0))))


def main():
    torch.manual_seed(SEED)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = GPT().to(device)
    opt = torch.optim.AdamW(model.parameters(), lr=LEARNING_RATE, weight_decay=WEIGHT_DECAY, betas=(0.9, 0.95))
    n_params = sum(p.numel() for p in model.parameters())
    print(f"device={device} params={n_params / 1e6:.2f}M budget={prepare.TIME_BUDGET_SECONDS:.0f}s")

    budget = prepare.TIME_BUDGET_SECONDS
    start, step = None, 0
    while True:
        if start is not None and time.perf_counter() - start >= budget:
            break
        progress = 0.0 if start is None else (time.perf_counter() - start) / budget
        for group in opt.param_groups:
            group["lr"] = lr_at(step, progress)
        x, y = prepare.get_batch(BATCH_SIZE, BLOCK_SIZE, device)
        with torch.autocast(device_type=device, dtype=torch.bfloat16, enabled=(device == "cuda")):
            logits = model(x)
        loss = F.cross_entropy(logits.float().view(-1, logits.size(-1)), y.view(-1))
        opt.zero_grad(set_to_none=True)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), GRAD_CLIP)
        opt.step()
        if start is None:  # start the clock after the first step so CUDA start-up is not counted
            if device == "cuda":
                torch.cuda.synchronize()
            start = time.perf_counter()
        step += 1
        if step % 200 == 0:
            print(f"step {step} loss {loss.item():.3f} lr {lr_at(step, progress):.5f}")

    print(f"trained {step} steps")
    prepare.evaluate(model)


if __name__ == "__main__":
    main()
