# Day 1 model decision

Selected `mobilenetv3_large_100_bg0_iw0.75` by mean held-out synthetic image accuracy; all candidates and per-fold evidence are in `v1/metrics.json`. Both black and paper fills were exposed during augmentation and compared on held-out piles; instance/window weights were also selected there.

Export averages the three layout-fold models into one ONNX graph. This retains the validated fold training procedure and uses every source in two members; an all-layout retrain has no held-out estimate in this dataset. The ensemble itself has no unbiased score on these source photos, so the reported metrics are fold predictions only. Architecture/config selection uses CV and is exploratory, not an independent test result.

FP32 retained. No INT8 accuracy claim or unvalidated quantization.
