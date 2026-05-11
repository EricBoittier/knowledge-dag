"""Runtime fixes for CSM + PEFT training (Transformers / Unsloth)."""

from __future__ import annotations

import types
<<<<<<< HEAD
from typing import Any
=======
>>>>>>> 74b0067 (Enhance audio snippet functionality and update project structure)

import torch
import torch.nn as nn
from transformers.loss.loss_utils import ForCausalLMLoss
from transformers.modeling_outputs import CausalLMOutputWithPast

<<<<<<< HEAD
_PATCH_CREATE_CAUSAL_MASK_ATTR = "_kd_csm_create_causal_mask_1d_fix"


def resolve_csm_core(model: nn.Module) -> nn.Module | None:
    """Find ``CsmForConditionalGeneration`` under Unsloth / PEFT wrappers."""
    m: nn.Module = model
    if hasattr(m, "base_model"):
        m = m.base_model
    if hasattr(m, "model") and not hasattr(m, "backbone_model"):
        m = m.model
    if hasattr(m, "backbone_model") and hasattr(m, "depth_decoder"):
        return m
    return None


def sync_csm_backbone_audio_embedding_from_depth(model: nn.Module) -> int:
    """Fix ``unsloth/csm-1b`` loads where backbone audio embeddings are random.

    The checkpoint omits ``backbone_model.embed_tokens.embed_audio_tokens.weight`` (it
    should match ``depth_decoder.model.embed_tokens.weight``). Hugging Face weight tying
    does not always run after Unsloth's loader, which breaks codec conditioning → gibberish audio.

    Returns 1 if weights were copied, 0 if already tied / shape mismatch / not CSM.
    """
    core = resolve_csm_core(model)
    if core is None:
        return 0
    bb_w = core.backbone_model.embed_tokens.embed_audio_tokens.weight
    dd_w = core.depth_decoder.model.embed_tokens.weight
    if bb_w.data_ptr() == dd_w.data_ptr():
        return 0
    if bb_w.shape != dd_w.shape or bb_w.dtype != dd_w.dtype:
        return 0
    with torch.no_grad():
        bb_w.copy_(dd_w)
    return 1


def patch_csm_create_causal_mask_for_1d_position_ids() -> None:
    """
    ``CsmDepthDecoderModel`` (Transformers 5.5) builds ``position_ids`` as a 1D ``arange(seq)`` and passes it to
    ``create_causal_mask``. ``masking_utils.find_packed_sequence_indices`` expects shape ``[batch, seq]`` and indexes
    ``position_ids[:, :1]``, which crashes on 1D tensors. Expand to ``[batch, seq]`` before the original implementation.
    ``CsmDepthDecoderModel`` calls ``create_causal_mask`` with keyword-only args (no positional ``inputs_embeds``),
    so the wrapper must read ``inputs_embeds`` from ``kwargs``.

    Also rebind ``modeling_csm.create_causal_mask`` — that module imports the function by value, not by reference.
    """
    import transformers.masking_utils as masking_utils
    from transformers.models.csm import modeling_csm

    if getattr(masking_utils, _PATCH_CREATE_CAUSAL_MASK_ATTR, False):
        return

    _orig: Any = masking_utils.create_causal_mask

    def _wrapped(*args: Any, **kwargs: Any) -> Any:
        position_ids = kwargs.get("position_ids")
        if position_ids is not None and position_ids.dim() == 1:
            inputs_embeds = kwargs.get("inputs_embeds")
            if inputs_embeds is None and len(args) >= 2:
                inputs_embeds = args[1]
            if (
                inputs_embeds is not None
                and hasattr(inputs_embeds, "shape")
                and inputs_embeds.ndim >= 2
            ):
                kwargs = dict(kwargs)
                b = int(inputs_embeds.shape[0])
                kwargs["position_ids"] = position_ids.unsqueeze(0).expand(b, -1).contiguous()
        return _orig(*args, **kwargs)

    _wrapped.__name__ = getattr(_orig, "__name__", "create_causal_mask")
    _wrapped.__doc__ = getattr(_orig, "__doc__", None)
    masking_utils.create_causal_mask = _wrapped
    modeling_csm.create_causal_mask = _wrapped
    setattr(masking_utils, _PATCH_CREATE_CAUSAL_MASK_ATTR, True)

=======
>>>>>>> 74b0067 (Enhance audio snippet functionality and update project structure)

def _hf_csm_depth_decoder_causal_lm_forward(
    self,
    input_ids=None,
    backbone_last_hidden_state=None,
    attention_mask=None,
    position_ids=None,
    past_key_values=None,
    inputs_embeds=None,
    labels=None,
    use_cache=None,
    logits_to_keep=0,
    **kwargs,
):
    """
    Matches Transformers ``CsmDepthDecoderForCausalLM.forward`` (codebook index math).
    Unsloth's patch passes ``cache_position`` into ``codebooks_head``; when it is None (training),
    that becomes ``codebook_indices is None`` and crashes. Official code uses
    ``torch.arange(seq_len) + past_seen_tokens``.
    """
    labels = kwargs.pop("labels", labels)
    past_seen_tokens = past_key_values.get_seq_length() if past_key_values is not None else 0
    batch_size = inputs_embeds.shape[0] if inputs_embeds is not None else input_ids.shape[0]
    seq_len = inputs_embeds.shape[1] if inputs_embeds is not None else input_ids.shape[1]
    device = inputs_embeds.device if inputs_embeds is not None else input_ids.device

    # Transformers 5.x masking_utils expects position_ids shaped [batch, seq]; some Trainer/Unsloth
    # paths pass a 1D [seq] tensor, which raises IndexError in find_packed_sequence_indices.
    if position_ids is not None:
        if position_ids.dim() == 1:
            n = position_ids.shape[0]
            if n == seq_len:
                position_ids = position_ids.unsqueeze(0).expand(batch_size, -1).contiguous()
            elif n == batch_size * seq_len:
                position_ids = position_ids.view(batch_size, seq_len).contiguous()
            else:
                position_ids = (
                    torch.arange(seq_len, device=device, dtype=position_ids.dtype)
                    .unsqueeze(0)
                    .expand(batch_size, -1)
                    .contiguous()
                )
        elif position_ids.dim() == 2 and position_ids.size(0) == 1 and batch_size > 1:
            position_ids = position_ids.expand(batch_size, -1).contiguous()

    codebook_indices = torch.arange(seq_len, device=device) + past_seen_tokens

<<<<<<< HEAD
    # Do not let kwargs override normalized position_ids (Unsloth may pass position_ids in **kwargs).
    kw2 = {k: v for k, v in kwargs.items() if k != "position_ids"}
=======
>>>>>>> 74b0067 (Enhance audio snippet functionality and update project structure)
    outputs = self.model(
        input_ids=input_ids,
        backbone_last_hidden_state=backbone_last_hidden_state,
        attention_mask=attention_mask,
        position_ids=position_ids,
        past_key_values=past_key_values,
        inputs_embeds=inputs_embeds,
        use_cache=use_cache,
<<<<<<< HEAD
        **kw2,
=======
        **kwargs,
>>>>>>> 74b0067 (Enhance audio snippet functionality and update project structure)
    )

    hidden_states = outputs[0]
    if isinstance(logits_to_keep, int):
        if logits_to_keep == 0:
            slice_indices = slice(1, None)
        else:
            slice_indices = slice(-logits_to_keep, None)
    else:
        slice_indices = logits_to_keep

    logits = self.codebooks_head(hidden_states[:, slice_indices, :], codebook_indices[slice_indices])
    logits = logits.contiguous()

    loss = None
    if labels is not None:
        shift_labels = labels[..., 1:].contiguous()
        loss_kw = {k: kwargs[k] for k in ("num_items_in_batch", "ignore_index") if k in kwargs}
        loss = ForCausalLMLoss(
            logits=logits,
            labels=None,
            vocab_size=self.config.vocab_size,
            shift_labels=shift_labels,
            **loss_kw,
        )

    return CausalLMOutputWithPast(
        loss=loss,
        logits=logits,
        past_key_values=outputs.past_key_values,
        hidden_states=outputs.hidden_states,
        attentions=outputs.attentions,
    )


def patch_depth_decoder_causal_lm_forward(model: nn.Module) -> int:
    """Replace Unsloth-broken ``CsmDepthDecoderForCausalLM.forward`` on each submodule."""
    n = 0
    for module in model.modules():
        if type(module).__name__ != "CsmDepthDecoderForCausalLM":
            continue
        if not hasattr(module, "codebooks_head") or not hasattr(module, "model"):
            continue
        if getattr(module, "_kd_depth_decoder_causal_lm_forward", False):
            continue
        module.forward = types.MethodType(_hf_csm_depth_decoder_causal_lm_forward, module)
        module._kd_depth_decoder_causal_lm_forward = True
        n += 1
    return n


def _depth_decoder_embed_clone_hook(_module, _input, output):
    """Return a fresh tensor so ``inputs_embeds[:, 0] = ...`` is not an in-place write on an embedding view."""
    return output.clone()


def patch_depth_decoder_embedding_clone(model: nn.Module) -> int:
    """
    ``CsmDepthDecoderModel`` does ``inputs_embeds[:, 0] = backbone_last_hidden_state``.
    Embedding outputs can be views of the weight leaf; PEFT/Unsloth can leave that incompatible with in-place
    slice assignment. A forward hook that returns ``output.clone()`` runs after ``embed_tokens`` and is harder
    to bypass than replacing ``forward`` (and avoids ``isinstance`` issues if ``modeling_csm`` was imported twice).
    """
    n = 0
    for module in model.modules():
        if type(module).__name__ != "CsmDepthDecoderModel":
            continue
        if not hasattr(module, "embed_tokens") or not hasattr(module, "inputs_embeds_projector"):
            continue
        if getattr(module, "_kd_depth_decoder_embed_hook", False):
            continue
        module.embed_tokens.register_forward_hook(_depth_decoder_embed_clone_hook)
        module._kd_depth_decoder_embed_hook = True
        n += 1
    return n
