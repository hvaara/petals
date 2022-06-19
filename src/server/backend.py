"""Code for serving bloom blocks via hivemind-server"""
from typing import Tuple, Sequence

import torch
from hivemind.moe.server.module_backend import ModuleBackend
from hivemind.moe.server.task_pool import TaskPool

from src.bloom.block import BloomBlock
from src.server.cache import MemoryCache

MAX_LENGTH = 2048


class TransformerBackend(ModuleBackend):
    """A wrapper for BloomBlock that can process requests for bloom layer forward, forward_incremental, and backward"""

    def __init__(self, *args, memory_cache: MemoryCache, **kwargs):
        super().__init__(*args, **kwargs)
        assert isinstance(self.module, BloomBlock)
        self.memory_cache = memory_cache

        for name, param in self.module.named_parameters():
            assert not param.requires_grad, f"Bloom layer parameters must not accumulate gradients, but {name} does"
        for name, buf in self.module.named_buffers():
            assert not buf.requires_grad, f"Bloom layer parameters must not accumulate gradients, but {name} does"

        self.inference_pool = TaskPool(self.inference_step, max_batch_size=1, name=f"{self.name}_inference")

    def inference_step(self, cache_metadata: torch.IntTensor, *inputs: torch.Tensor) -> Tuple[torch.Tensor, ...]:
        attention_cache_handle = int(cache_metadata[0, 0].item())
        current_sequence_length = int(cache_metadata[0, 1].item())
        with self.memory_cache.use_cache(attention_cache_handle) as cache:
            print('METADATA:', cache_metadata, "CACHE", cache.mean(), "CACHE ENTRIES:", len(self.memory_cache._allocated_tensors))
            cache[...] += 1
            return (inputs[0] + cache.flatten()[0],)

    def get_pools(self) -> Sequence[TaskPool]:
        return self.forward_pool, self.backward_pool, self.inference_pool