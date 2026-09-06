"""Run a resumable COLMAP + OpenMVS textured-mesh reconstruction."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import time
from pathlib import Path


def prepare_openmvs_masks(dense_images: Path, src_masks: Path, dst: Path) -> Path | None:
    try:
        from PIL import Image
    except ImportError:
        return None
    images = sorted(dense_images.glob("*.jpg"))
    if not images:
        return None
    dst.mkdir(parents=True, exist_ok=True)
    for image_path in images:
        source = next(
            (
                candidate
                for candidate in (
                    src_masks / f"{image_path.name}.mask.png",
                    src_masks / f"{image_path.stem}.mask.png",
                    src_masks / f"{image_path.name}.png",
                )
                if candidate.exists()
            ),
            None,
        )
        if source is None:
            shutil.rmtree(dst, ignore_errors=True)
            return None
        with Image.open(image_path) as image, Image.open(source) as mask:
            mask = mask.convert("L")
            if mask.size != image.size:
                mask = mask.resize(image.size, Image.Resampling.NEAREST)
            mask.save(dst / f"{image_path.stem}.mask.png")
    return dst


def find_executable(root: Path, name: str) -> Path:
    matches = sorted(root.rglob(name))
    if not matches:
        raise FileNotFoundError(f"Could not find {name} below {root}")
    return matches[0]


def run_stage(
    name: str,
    command: list[str],
    log_dir: Path,
    marker_dir: Path,
    force: bool,
    cwd: Path | None = None,
) -> None:
    marker = marker_dir / f"{name}.done"
    if marker.exists() and not force:
        print(f"  {name}: cached")
        return

    log_dir.mkdir(parents=True, exist_ok=True)
    marker_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{name}.log"
    started = time.time()
    print(f"  {name}: running")
    with log_path.open("w", encoding="utf-8", errors="replace") as log:
        log.write(subprocess.list2cmdline(command) + "\n\n")
        log.flush()
        result = subprocess.run(
            command,
            cwd=cwd,
            stdout=log,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    if result.returncode != 0:
        marker.unlink(missing_ok=True)
        raise subprocess.CalledProcessError(result.returncode, command)
    marker.write_text(
        json.dumps(
            {
                "name": name,
                "elapsed_seconds": round(time.time() - started, 3),
                "command": command,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def choose_sparse_model(sparse_root: Path) -> Path:
    candidates = [
        path
        for path in sparse_root.iterdir()
        if path.is_dir() and (path / "images.bin").exists()
    ]
    if not candidates:
        raise RuntimeError(f"COLMAP did not create a sparse model in {sparse_root}")
    return max(candidates, key=lambda path: (path / "images.bin").stat().st_size)


def select_image_list(image_paths: list[Path], max_images: int) -> list[Path]:
    if max_images <= 0 or len(image_paths) <= max_images:
        return image_paths
    if max_images == 1:
        return image_paths[:1]
    step = (len(image_paths) - 1) / (max_images - 1)
    chosen: list[Path] = []
    seen: set[int] = set()
    for index in range(max_images):
        source_index = min(int(round(index * step)), len(image_paths) - 1)
        if source_index not in seen:
            seen.add(source_index)
            chosen.append(image_paths[source_index])
    return chosen


def reconstruct_item(
    root: Path,
    item_id: str,
    colmap: Path,
    openmvs: Path,
    force: bool,
    refine: bool,
    max_image_size: int,
    use_gpu: bool,
    max_images: int,
) -> dict:
    item_root = root / "work" / "photogrammetry" / item_id
    images = item_root / "images"
    masks = item_root / "masks"
    mvs_masks = item_root / "mvs_masks"
    database = item_root / "database.db"
    sparse = item_root / "sparse"
    dense = item_root / "dense"
    mvs = item_root / "mvs"
    logs = item_root / "logs"
    markers = item_root / "stages"
    gpu_flag = "1" if use_gpu else "0"

    image_paths = sorted(images.glob("*.jpg"))
    if not image_paths:
        raise RuntimeError(f"No flattened input frames found for {item_id}: {images}")
    selected_images = select_image_list(image_paths, max_images)
    image_list = item_root / "image_list.txt"
    image_list.write_text(
        "\n".join(path.name for path in selected_images) + "\n",
        encoding="utf-8",
    )

    use_masks = (
        all((masks / f"{path.name}.png").exists() for path in selected_images)
        and all((mvs_masks / f"{path.name}.mask.png").exists() for path in selected_images)
    )
    sparse.mkdir(parents=True, exist_ok=True)
    dense.mkdir(parents=True, exist_ok=True)
    mvs.mkdir(parents=True, exist_ok=True)
    if force or not (markers / "01_features.done").exists():
        database.unlink(missing_ok=True)

    feature_command = [
        str(colmap),
        "feature_extractor",
        "--database_path",
        str(database),
        "--image_path",
        str(images),
        "--image_list_path",
        str(image_list),
        "--ImageReader.single_camera",
        "1",
        "--ImageReader.camera_model",
        "SIMPLE_RADIAL",
        "--FeatureExtraction.type",
        "SIFT",
        "--FeatureExtraction.use_gpu",
        gpu_flag,
        "--FeatureExtraction.num_threads",
        "8",
        "--FeatureExtraction.max_image_size",
        str(max_image_size),
        "--SiftExtraction.max_num_features",
        "8192",
        "--SiftExtraction.peak_threshold",
        "0.006",
    ]
    # Keep background features for camera pose; object masks are applied later in OpenMVS.
    run_stage("01_features", feature_command, logs, markers, force)

    run_stage(
        "02_matching",
        [
            str(colmap),
            "exhaustive_matcher",
            "--database_path",
            str(database),
            "--FeatureMatching.type",
            "SIFT_BRUTEFORCE",
            "--FeatureMatching.use_gpu",
            gpu_flag,
            "--FeatureMatching.guided_matching",
            "1",
            "--FeatureMatching.max_num_matches",
            "16384",
            "--FeatureMatching.num_threads",
            "8",
        ],
        logs,
        markers,
        force,
    )

    run_stage(
        "03_mapping",
        [
            str(colmap),
            "mapper",
            "--database_path",
            str(database),
            "--image_path",
            str(images),
            "--output_path",
            str(sparse),
            "--Mapper.min_num_matches",
            "12",
            "--Mapper.ba_use_gpu",
            gpu_flag,
            "--Mapper.num_threads",
            "8",
        ],
        logs,
        markers,
        force,
    )

    sparse_model = choose_sparse_model(sparse)
    run_stage(
        "03b_sparse_txt",
        [
            str(colmap),
            "model_converter",
            "--input_path",
            str(sparse_model),
            "--output_path",
            str(sparse_model),
            "--output_type",
            "TXT",
        ],
        logs,
        markers,
        force,
    )
    run_stage(
        "04_undistort",
        [
            str(colmap),
            "image_undistorter",
            "--image_path",
            str(images),
            "--input_path",
            str(sparse_model),
            "--output_path",
            str(dense),
            "--output_type",
            "COLMAP",
            "--max_image_size",
            str(max_image_size),
        ],
        logs,
        markers,
        force,
    )

    run_stage(
        "04b_dense_txt",
        [
            str(colmap),
            "model_converter",
            "--input_path",
            str(dense / "sparse"),
            "--output_path",
            str(dense / "sparse"),
            "--output_type",
            "TXT",
        ],
        logs,
        markers,
        force,
    )

    scene = mvs / "scene.mvs"
    run_stage(
        "05_interface_colmap",
        [
            str(openmvs / "InterfaceCOLMAP.exe"),
            "--working-folder",
            str(mvs),
            "--input-file",
            str(dense),
            "--image-folder",
            str(dense / "images"),
            "--output-file",
            str(scene),
        ],
        logs,
        markers,
        force,
    )

    dense_scene = mvs / "scene_dense.mvs"
    densify_command = [
        str(openmvs / "DensifyPointCloud.exe"),
        "--working-folder",
        str(mvs),
        "--input-file",
        str(scene),
        "--output-file",
        str(dense_scene),
        "--resolution-level",
        "2",
        "--number-views",
        "4",
        "--cuda-device",
        "-2",
    ]
    prepared_masks = prepare_openmvs_masks(dense / "images", mvs_masks, mvs / "masks")
    if prepared_masks is not None:
        densify_command.extend(
            [
                "--mask-path",
                str(prepared_masks),
                "--ignore-mask-label",
                "0",
            ]
        )
    run_stage("06_densify", densify_command, logs, markers, force)

    dense_cloud = mvs / "scene_dense.ply"
    mesh_scene = mvs / "scene_mesh.mvs"
    mesh_file = mvs / "scene_mesh.ply"
    run_stage(
        "07_mesh",
        [
            str(openmvs / "ReconstructMesh.exe"),
            "--working-folder",
            str(mvs),
            "--input-file",
            str(dense_scene),
            "--pointcloud-file",
            str(dense_cloud),
            "--output-file",
            str(mesh_scene),
            "--close-holes",
            "30",
            "--smooth",
            "2",
        ],
        logs,
        markers,
        force,
    )

    texture_mesh = mesh_file
    if refine:
        refined_scene = mvs / "scene_refined.mvs"
        refined_mesh = mvs / "scene_refined.ply"
        run_stage(
            "08_refine",
            [
                str(openmvs / "RefineMesh.exe"),
                "--working-folder",
                str(mvs),
                "--input-file",
                str(dense_scene),
                "--mesh-file",
                str(mesh_file),
                "--output-file",
                str(refined_scene),
                "--resolution-level",
                "1",
            ],
            logs,
            markers,
            force,
        )
        generated_refined = mvs / "scene_refined.ply"
        if generated_refined.exists():
            texture_mesh = generated_refined

    textured_scene = mvs / "scene_textured.mvs"
    texture_command = [
        str(openmvs / "TextureMesh.exe"),
        "--working-folder",
        str(mvs),
        "--input-file",
        str(dense_scene),
        "--mesh-file",
        str(texture_mesh),
        "--output-file",
        str(textured_scene),
        "--export-type",
        "obj",
    ]
    run_stage(
        "09_texture",
        texture_command,
        logs,
        markers,
        force,
    )

    obj_path = mvs / "scene_textured.obj"
    glb_path = mvs / "scene_textured.glb"
    blender = Path(r"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe")
    if obj_path.exists() and blender.exists() and (force or not glb_path.exists()):
        convert_script = item_root / "convert_obj.py"
        convert_script.write_text(
            "\n".join(
                [
                    "import bpy",
                    "bpy.ops.wm.read_factory_settings(use_empty=True)",
                    f"bpy.ops.wm.obj_import(filepath=r'{obj_path}')",
                    f"bpy.ops.export_scene.gltf(filepath=r'{glb_path}', export_format='GLB')",
                ]
            ),
            encoding="utf-8",
        )
        run_stage(
            "10_glb",
            [str(blender), "--background", "--python", str(convert_script)],
            logs,
            markers,
            force,
        )

    glb_files = sorted(mvs.glob("*.glb"), key=lambda path: path.stat().st_mtime)
    for leftover in (dense / "stereo",):
        if leftover.exists():
            shutil.rmtree(leftover, ignore_errors=True)
    for dmap in mvs.glob("*.dmap"):
        dmap.unlink(missing_ok=True)
    result = {
        "item_id": item_id,
        "input_frames": len(image_paths),
        "masks_used": use_masks,
        "sparse_model": str(sparse_model),
        "dense_cloud": str(dense_cloud) if dense_cloud.exists() else None,
        "mesh": str(texture_mesh) if texture_mesh.exists() else None,
        "textured_glb": str(glb_files[-1]) if glb_files else None,
    }
    (item_root / "reconstruction.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
    )
    parser.add_argument("--items", nargs="+", required=True)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--refine", action="store_true")
    parser.add_argument("--max-image-size", type=int, default=960)
    parser.add_argument("--max-images", type=int, default=48)
    parser.add_argument("--use-gpu", action="store_true")
    args = parser.parse_args()

    root = args.root.resolve()
    colmap = find_executable(root / "tools" / "colmap", "colmap.exe")
    openmvs = root / "tools" / "openmvs"
    required = [
        openmvs / "InterfaceCOLMAP.exe",
        openmvs / "DensifyPointCloud.exe",
        openmvs / "ReconstructMesh.exe",
        openmvs / "TextureMesh.exe",
    ]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise FileNotFoundError("Missing OpenMVS tools: " + ", ".join(missing))

    results = []
    for item_id in args.items:
        print(f"{item_id}:")
        try:
            results.append(
                reconstruct_item(
                    root,
                    item_id,
                    colmap,
                    openmvs,
                    args.force,
                    args.refine,
                    args.max_image_size,
                    args.use_gpu,
                    args.max_images,
                )
            )
        except Exception as exc:
            results.append({"item_id": item_id, "error": repr(exc)})
            print(f"  ERROR: {exc}")

    summary_path = root / "reports" / "photogrammetry_results.json"
    summary_path.write_text(
        json.dumps(results, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(results, ensure_ascii=False, indent=2))
    if any("error" in result for result in results):
        raise SystemExit("One or more reconstructions failed.")


if __name__ == "__main__":
    main()
