from __future__ import annotations

from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image


def _center_mask(image: np.ndarray) -> np.ndarray:
    """Deterministic non-model fallback using GrabCut and a centre prior."""
    height, width = image.shape[:2]
    mask = np.zeros((height, width), np.uint8)
    margin_x, margin_y = max(2, width // 12), max(2, height // 12)
    rectangle = (margin_x, margin_y, max(1, width - 2 * margin_x), max(1, height - 2 * margin_y))
    background = np.zeros((1, 65), np.float64)
    foreground = np.zeros((1, 65), np.float64)
    try:
        cv2.grabCut(image, mask, rectangle, background, foreground, 4, cv2.GC_INIT_WITH_RECT)
        result = np.where((mask == cv2.GC_FGD) | (mask == cv2.GC_PR_FGD), 255, 0).astype(np.uint8)
    except cv2.error:
        result = np.zeros((height, width), np.uint8)
        result[margin_y : height - margin_y, margin_x : width - margin_x] = 255
    components, labels, stats, centroids = cv2.connectedComponentsWithStats(result)
    if components <= 1:
        return result
    centre = np.asarray([width / 2, height / 2])
    best = max(
        range(1, components),
        key=lambda index: float(stats[index, cv2.CC_STAT_AREA]) / (1.0 + np.linalg.norm(centroids[index] - centre) / max(width, height)),
    )
    return np.where(labels == best, 255, 0).astype(np.uint8)


def _sam2_mask(image: np.ndarray, model_id: str, min_area_fraction: float, max_area_fraction: float) -> np.ndarray:
    try:
        from sam2.automatic_mask_generator import SAM2AutomaticMaskGenerator
    except ImportError as error:  # pragma: no cover - only exercised on a GPU host
        raise RuntimeError("SAM2 is not installed. Run scripts/bootstrap_models.py --sam2 first, or set segmentation.backend=center.") from error
    generator = SAM2AutomaticMaskGenerator.from_pretrained(
        model_id,
        points_per_side=32,
        pred_iou_thresh=0.80,
        stability_score_thresh=0.95,
        crop_n_layers=1,
        min_mask_region_area=400,
    )
    annotations = generator.generate(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))
    height, width = image.shape[:2]
    centre = np.asarray([width / 2, height / 2])
    candidates: list[tuple[float, np.ndarray]] = []
    for annotation in annotations:
        fraction = float(annotation["area"]) / float(width * height)
        if not min_area_fraction <= fraction <= max_area_fraction:
            continue
        x, y, box_width, box_height = annotation["bbox"]
        box_centre = np.asarray([x + box_width / 2, y + box_height / 2])
        centrality = 1.0 - min(1.0, float(np.linalg.norm(box_centre - centre)) / (0.55 * max(width, height)))
        score = 0.55 * float(annotation["predicted_iou"]) + 0.30 * float(annotation["stability_score"]) + 0.15 * centrality
        candidates.append((score, np.asarray(annotation["segmentation"], dtype=np.uint8) * 255))
    if not candidates:
        raise RuntimeError("SAM2 found no plausible centred foreground; inspect the task contact sheet and retry with segmentation.backend=center")
    return max(candidates, key=lambda pair: pair[0])[1]


def make_conditioning_image(source: Path, output: Path, segmentation: dict[str, Any]) -> dict[str, Any]:
    image = cv2.imread(str(source), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError(f"could not read selected view: {source}")
    backend = str(segmentation["backend"])
    if backend == "center":
        mask = _center_mask(image)
    elif backend == "sam2":
        mask = _sam2_mask(
            image,
            str(segmentation["sam2_model"]),
            float(segmentation["min_area_fraction"]),
            float(segmentation["max_area_fraction"]),
        )
    else:
        raise ValueError(f"unknown segmentation backend: {backend}")
    x, y, width, height = cv2.boundingRect(mask)
    if width <= 2 or height <= 2:
        raise RuntimeError(f"foreground mask is empty: {source}")
    padding = max(4, round(0.06 * max(width, height)))
    x0, y0 = max(0, x - padding), max(0, y - padding)
    x1, y1 = min(image.shape[1], x + width + padding), min(image.shape[0], y + height + padding)
    cropped_bgr = image[y0:y1, x0:x1]
    cropped_mask = mask[y0:y1, x0:x1]
    rgba = cv2.cvtColor(cropped_bgr, cv2.COLOR_BGR2RGBA)
    rgba[:, :, 3] = cropped_mask
    output.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(rgba).save(output)
    return {
        "source": str(source), "output": str(output), "backend": backend,
        "crop_xyxy": [int(x0), int(y0), int(x1), int(y1)],
        "mask_area_fraction": float((mask > 0).mean()),
        "crop_width": int(x1 - x0), "crop_height": int(y1 - y0),
    }
