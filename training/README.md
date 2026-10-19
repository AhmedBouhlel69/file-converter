# Optional model development

This directory is separate from the desktop runtime. No training dependencies,
datasets, checkpoints or training workers are included in the app build.

Start with [the training and optimization guide](../docs/TRAINING_AND_OPTIMIZATION.md).
It contains the data contract, setup, guarded fine-tuning/export/evaluation commands,
promotion criteria and explicit verification limits.

No trained model is supplied by these tools. A local upstream U2NETP checkpoint
and a human-reviewed paired image/alpha dataset are required.
