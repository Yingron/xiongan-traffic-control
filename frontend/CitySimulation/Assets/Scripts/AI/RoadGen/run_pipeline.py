import argparse
import datetime
import json
import os
import shutil
from typing import Any, Dict

from llm_client import LlmClient
from road_extract import extract


def read_text(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def write_text(path: str, content: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def safe_json_parse(text: str) -> Dict[str, Any]:
    text = text.strip()
    if text.startswith("{") and text.endswith("}"):
        return json.loads(text)
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("No JSON object found in LLM response")
    return json.loads(text[start : end + 1])


def validate_map_json(obj: Dict[str, Any]) -> None:
    if "snapshot" not in obj:
        raise ValueError("Missing snapshot")
    snap = obj["snapshot"]
    for key in ["roads", "buildings", "vehicles", "trafficLights"]:
        if key not in snap:
            raise ValueError(f"Missing snapshot.{key}")
    if snap["vehicles"] != []:
        raise ValueError("vehicles must be []")
    if snap["trafficLights"] != []:
        raise ValueError("trafficLights must be []")
    if not isinstance(snap["roads"], list):
        raise ValueError("roads must be list")
    if not isinstance(snap["buildings"], list):
        raise ValueError("buildings must be list")


def main():
    parser = argparse.ArgumentParser(description="End-to-end road generation pipeline")
    parser.add_argument("--image", required=True, help="Input image path")
    parser.add_argument("--extra_prompt", default="", help="Extra prompt to influence layout")
    parser.add_argument("--history_dir", default="history", help="History directory")
    parser.add_argument("--prompt_template", default="prompts/map_json_prompt.txt")
    parser.add_argument("--lower_hsv", nargs=3, type=int, default=[0, 0, 180])
    parser.add_argument("--upper_hsv", nargs=3, type=int, default=[180, 60, 255])
    parser.add_argument("--morph_ksize", type=int, default=11)
    parser.add_argument("--simplify_eps", type=float, default=200.0)
    parser.add_argument("--resample_step", type=float, default=400.0)
    parser.add_argument("--target_points_min", type=int, default=5)
    parser.add_argument("--target_points_max", type=int, default=7)
    parser.add_argument("--min_branch_len", type=float, default=10.0)
    parser.add_argument("--unity_scale", type=float, default=1.0)
    args = parser.parse_args()

    script_dir = os.path.dirname(os.path.abspath(__file__))
    history_root = os.path.join(script_dir, args.history_dir)
    time_dir = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = os.path.join(history_root, time_dir)
    os.makedirs(run_dir, exist_ok=True)

    img_copy = os.path.join(run_dir, os.path.basename(args.image))
    shutil.copyfile(args.image, img_copy)

    params = {
        "lower_hsv": args.lower_hsv,
        "upper_hsv": args.upper_hsv,
        "morph_ksize": args.morph_ksize,
        "simplify_eps": args.simplify_eps,
        "resample_step": args.resample_step,
        "target_points_min": args.target_points_min,
        "target_points_max": args.target_points_max,
        "min_branch_len": args.min_branch_len,
        "unity_scale": args.unity_scale,
    }

    extract_out = extract(img_copy, run_dir, params)
    roads_keypoints_path = extract_out["roads_keypoints"]

    prompt_template_path = os.path.join(script_dir, args.prompt_template)
    template = read_text(prompt_template_path)
    polylines_json = read_text(roads_keypoints_path)

    prompt = template.replace("{{POLYLINES_JSON}}", polylines_json)
    prompt = prompt.replace("{{EXTRA_PROMPT}}", args.extra_prompt)

    write_text(os.path.join(run_dir, "prompt.txt"), prompt)

    meta = {
        "input_image": img_copy,
        "extra_prompt": args.extra_prompt,
        "params": params,
        "prompt_template": prompt_template_path,
    }
    write_text(os.path.join(run_dir, "run_meta.json"), json.dumps(meta, indent=2))

    client = LlmClient()
    if not client.is_configured():
        write_text(os.path.join(run_dir, "response.txt"), "LLM_API_KEY not set")
        print("LLM_API_KEY not set. Prompt saved; provide LLM response manually.")
        return

    response = client.generate(prompt)
    write_text(os.path.join(run_dir, "response.txt"), response)

    parsed = safe_json_parse(response)
    validate_map_json(parsed)

    out_path = os.path.join(run_dir, "map.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(parsed, f, indent=2)

    print(f"Saved map JSON to {out_path}")


if __name__ == "__main__":
    main()
