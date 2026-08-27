"""Sample-exact amended Stage 4A FMA-30 audio geometry."""
from __future__ import annotations
import hashlib, math
from dataclasses import dataclass
from pathlib import Path
import numpy as np
import torch, torchaudio

SAMPLE_RATE=24000; WINDOW_SAMPLES=120000; MINIMUM_SAMPLES=round(29.5*SAMPLE_RATE)
CENTERS=(3,5,9,15,21,25,27)
METHOD_CENTERS={"CENTER5":(15,),"UNIFORM3_MEAN":(5,15,25),"UNIFORM5_MEAN":(3,9,15,21,27)}

class Stage4AError(ValueError): pass
@dataclass(frozen=True)
class Window:
    index:int; center_sec:int; start_sample:int; end_sample:int

def windows_for(sample_count:int, centers:tuple[int,...]=CENTERS)->list[Window]:
    if sample_count<WINDOW_SAMPLES: raise Stage4AError("cannot support a complete 5-second window")
    output=[]
    for index,center_sec in enumerate(centers):
        center=math.floor(center_sec*SAMPLE_RATE+0.5)
        start=min(max(center-WINDOW_SAMPLES//2,0),sample_count-WINDOW_SAMPLES)
        output.append(Window(index,center_sec,start,start+WINDOW_SAMPLES))
    if len({(x.start_sample,x.end_sample) for x in output})!=len(output): raise Stage4AError("cannot preserve distinct frozen windows")
    return output

def cache_windows(sample_count:int)->list[Window]:
    if sample_count<MINIMUM_SAMPLES: raise Stage4AError(f"requires at least {MINIMUM_SAMPLES} samples")
    return windows_for(sample_count)

def method_windows(method:str,sample_count:int)->list[Window]:
    if method not in METHOD_CENTERS: raise Stage4AError(f"unknown method {method}")
    return windows_for(sample_count,METHOD_CENTERS[method])

def canonical_waveform(waveform:torch.Tensor,source_rate:int)->torch.Tensor:
    if waveform.ndim==1: waveform=waveform.unsqueeze(0)
    if waveform.ndim!=2 or waveform.shape[1]<1 or source_rate<=0 or not torch.isfinite(waveform).all(): raise Stage4AError("invalid decode")
    waveform=waveform.to(torch.float32).mean(dim=0,keepdim=True)
    if source_rate!=SAMPLE_RATE: waveform=torchaudio.functional.resample(waveform,source_rate,SAMPLE_RATE)
    return waveform.squeeze(0).contiguous()

def decode(path:str|Path)->torch.Tensor:
    try: waveform,rate=torchaudio.load(str(path))
    except Exception as exc: raise Stage4AError(f"decode failed for {path}: {exc}") from exc
    return canonical_waveform(waveform,rate)

def pcm_sha256(waveform:torch.Tensor)->str:
    return hashlib.sha256(np.asarray(waveform.cpu(),dtype='<f4').tobytes()).hexdigest()
