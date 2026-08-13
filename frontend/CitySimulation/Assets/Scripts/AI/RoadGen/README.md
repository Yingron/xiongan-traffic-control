# RoadGen

Image to map JSON pipeline with OpenCV road extraction and LLM-based map completion.

## What it does
- Extract road polylines from an input image using OpenCV.
- Send road polylines plus an extra prompt to an LLM to add buildings and output map JSON.
- Save all intermediate artifacts and history for traceability.

## Folder layout
- prompts/ : prompt templates used for the LLM
- history/ : per-run outputs and intermediate files
- road_extract.py : OpenCV extraction for road polylines
- llm_client.py : minimal OpenAI-compatible client (env-based)
- run_pipeline.py : end-to-end runner

## Requirements
- Python 3.9+
- opencv-contrib-python (for skeleton thinning)
- numpy

Install:

```
pip install opencv-contrib-python numpy
```

## Quick start

```
python Assets\Scripts\AI\RoadGen\run_pipeline.py --image "Assets\Scripts\AI\manual\sample.jpg"
```

Artifacts are saved under history/YYYYMMDD_HHMMSS/.

## Environment variables
- LLM_API_KEY: required for live LLM calls
- LLM_BASE_URL: optional, defaults to https://api.openai.com/v1
- LLM_MODEL: optional, defaults to gpt-4o-mini

If LLM_API_KEY is not set, the pipeline will write the prompt and exit with a warning.
