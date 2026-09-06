from __future__ import annotations

import importlib
import gc
import sys
from pathlib import Path
from typing import Any

import numpy as np
import trimesh
from PIL import Image


def _primitive_mesh(image_path: Path) -> trimesh.Trimesh:
    image = Image.open(image_path).convert("RGBA")
    width, height = image.size
    aspect = max(0.35, min(2.6, width / max(height, 1)))
    # A shallow closed cuboid is safer than a textured plane in a physics engine.
    return trimesh.creation.box(extents=(aspect, 0.28, 1.0))


def _load_mesh(path: Path) -> trimesh.Trimesh:
    loaded = trimesh.load(path, force="scene")
    if isinstance(loaded, trimesh.Scene):
        meshes = [geometry for geometry in loaded.geometry.values() if isinstance(geometry, trimesh.Trimesh)]
        if not meshes:
            raise RuntimeError(f"Hunyuan output has no mesh: {path}")
        if len(meshes) == 1:
            # Do not concatenate a one-mesh textured OBJ: trimesh's generic
            # concatenate path can replace TextureVisuals with vertex colours.
            mesh = meshes[0].copy()
        else:
            textured = [
                geometry
                for geometry in meshes
                if getattr(getattr(getattr(geometry, "visual", None), "material", None), "image", None) is not None
            ]
            if textured:
                raise RuntimeError(
                    f"Hunyuan output has {len(meshes)} textured geometries; "
                    "this baseline writes one USD material and refuses to silently discard texture assignments"
                )
            mesh = trimesh.util.concatenate(meshes)
    elif isinstance(loaded, trimesh.Trimesh):
        mesh = loaded
    else:
        raise RuntimeError(f"unsupported mesh payload: {type(loaded).__name__}")
    if len(mesh.faces) == 0:
        raise RuntimeError(f"empty mesh: {path}")
    return mesh


def _export_result(mesh: Any, output: Path) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(mesh, (str, Path)):
        source = Path(mesh)
        if source.resolve() != output.resolve():
            output.write_bytes(source.read_bytes())
        return output
    if hasattr(mesh, "export"):
        mesh.export(str(output))
        return output
    if hasattr(mesh, "save"):
        mesh.save(str(output))
        return output
    raise TypeError(f"cannot export Hunyuan mesh type: {type(mesh).__name__}")


class HunyuanReconstructor:
    """One GPU model session reused across every task in a run.

    Loading both Hunyuan Shape and Paint for every one of 34 assets is not a
    viable GPU workflow: it needlessly downloads/initializes models, lengthens
    the run and can fragment VRAM.  This session is made exactly once by the
    pipeline and then processes each conditioning image in turn.
    """

    def __init__(self, reconstruction: dict[str, Any]) -> None:
        self.reconstruction = reconstruction
        self.load_mode = str(reconstruction.get("hunyuan_load_mode", "resident"))
        if self.load_mode not in {"resident", "sequential"}:
            raise ValueError(f"unsupported hunyuan_load_mode: {self.load_mode}")
        self.repo = Path(str(reconstruction["hunyuan_repo"])).resolve()
        if not self.repo.is_dir():
            raise FileNotFoundError(f"Hunyuan3D checkout not found: {self.repo}; run scripts/bootstrap_models.py --hunyuan")
        for relative in ("hy3dshape", "hy3dpaint"):
            candidate = str(self.repo / relative)
            if candidate not in sys.path:
                sys.path.insert(0, candidate)
        self.shape_pipeline: Any | None = self._load_shape_pipeline()
        self.paint_pipeline: Any | None = None
        if self.wants_texture and self.load_mode == "resident":
            self.paint_pipeline = self._load_paint_pipeline()

    @property
    def wants_texture(self) -> bool:
        return bool(self.reconstruction.get("hunyuan_texture", True))

    @property
    def sequential(self) -> bool:
        return self.load_mode == "sequential"

    def _load_shape_pipeline(self) -> Any:
        try:  # imports are deliberately lazy so CPU-only validation has no model dependency
            from hy3dshape.pipelines import Hunyuan3DDiTFlowMatchingPipeline
        except ImportError as error:  # pragma: no cover - GPU-only integration
            raise RuntimeError("Hunyuan3D dependencies are unavailable; follow README section 'GPU install'.") from error
        return Hunyuan3DDiTFlowMatchingPipeline.from_pretrained(str(self.reconstruction["hunyuan_model"]))

    def _load_paint_pipeline(self) -> Any:
        try:
            texture_module = importlib.import_module("textureGenPipeline")
            paint_config = texture_module.Hunyuan3DPaintConfig(
                max_num_view=int(self.reconstruction.get("hunyuan_paint_max_views", 6)),
                resolution=int(self.reconstruction.get("hunyuan_paint_resolution", 512)),
            )
            # Hunyuan's own demo is run from its checkout. The baseline is
            # invoked elsewhere, so resolve its local files explicitly.
            paint_config.realesrgan_ckpt_path = str(self.repo / "hy3dpaint" / "ckpt" / "RealESRGAN_x4plus.pth")
            paint_config.multiview_cfg_path = str(self.repo / "hy3dpaint" / "cfgs" / "hunyuan-paint-pbr.yaml")
            paint_config.custom_pipeline = str(self.repo / "hy3dpaint" / "hunyuanpaintpbr")
            return texture_module.Hunyuan3DPaintPipeline(paint_config)
        except Exception as error:  # pragma: no cover - GPU-only integration
            raise RuntimeError("Hunyuan texture pipeline could not initialize; do not silently publish an untextured high profile.") from error

    def generate_shape(self, image_path: Path, shape_path: Path) -> Path:
        if self.shape_pipeline is None:
            raise RuntimeError("Hunyuan shape model was released before all shapes were generated")
        generated = self.shape_pipeline(image=str(image_path))[0]
        return _export_result(generated, shape_path)

    def begin_texture_phase(self) -> None:
        """Release Shape before loading Paint on a 24 GiB GPU."""
        if not self.sequential or not self.wants_texture:
            return
        self.shape_pipeline = None
        gc.collect()
        try:  # pragma: no cover - exercised only on a CUDA host
            import torch
            torch.cuda.empty_cache()
        except Exception:
            pass
        self.paint_pipeline = self._load_paint_pipeline()

    def generate_texture(self, shape_path: Path, image_path: Path, output: Path) -> Path:
        if not self.wants_texture:
            return shape_path
        if self.paint_pipeline is None:
            raise RuntimeError("Hunyuan Paint is not initialized; call begin_texture_phase() first in sequential mode")
        try:
            textured = self.paint_pipeline(
                mesh_path=str(shape_path),
                image_path=str(image_path),
                output_mesh_path=str(output),
            )
            return Path(str(textured))
        except Exception as error:  # pragma: no cover - GPU-only integration
            raise RuntimeError("Hunyuan shape generation succeeded but texture generation failed; do not silently publish an untextured high profile.") from error

    def reconstruct(self, image_path: Path, output: Path) -> trimesh.Trimesh:
        shape_path = output.with_name(output.stem + "_shape.glb")
        self.generate_shape(image_path, shape_path)
        final_path = self.generate_texture(shape_path, image_path, output.with_name(output.stem + "_textured.obj"))
        return _load_mesh(final_path)


def create_reconstructor(reconstruction: dict[str, Any]) -> HunyuanReconstructor | None:
    backend = str(reconstruction["backend"])
    if backend == "primitive":
        return None
    if backend == "hunyuan":
        return HunyuanReconstructor(reconstruction)
    raise ValueError(f"unknown reconstruction backend: {backend}")


def finalize_mesh(task_id: str, mesh: trimesh.Trimesh, output: Path, reconstruction: dict[str, Any], source: str) -> dict[str, Any]:
    """Normalize, simplify and export a mesh after any reconstruction backend."""
    backend = str(reconstruction["backend"])
    source_faces = int(len(mesh.faces))
    simplification_error: str | None = None
    if len(mesh.faces) > int(reconstruction["max_faces"]):
        try:
            mesh = mesh.simplify_quadric_decimation(int(reconstruction["max_faces"]))
        except Exception as error:
            # The optional trimesh decimator has platform-specific native
            # dependencies. Keep a valid mesh and expose the condition in the
            # manifest rather than replacing it with a lower-quality primitive.
            simplification_error = f"{type(error).__name__}: {error}"
    if len(mesh.faces) == 0:
        raise RuntimeError(f"reconstruction produced no faces: {task_id}")
    mesh.remove_unreferenced_vertices()
    extent = np.asarray(mesh.extents, dtype=np.float64)
    scale = 1.0 / max(float(extent.max()), 1e-6)
    mesh.apply_scale(scale)
    mesh.apply_translation(-mesh.bounds.mean(axis=0))
    mesh.apply_translation([0.0, 0.0, -float(mesh.bounds[0, 2])])
    output.parent.mkdir(parents=True, exist_ok=True)
    mesh.export(str(output))
    return {"task_id": task_id, "backend": backend, "source": source, "mesh": str(output), "vertices": int(len(mesh.vertices)), "faces": int(len(mesh.faces)), "source_faces": source_faces, "simplification_error": simplification_error, "extent": [float(value) for value in mesh.extents]}


def reconstruct_mesh(
    task_id: str,
    conditioning_image: Path,
    output: Path,
    reconstruction: dict[str, Any],
    *,
    reconstructor: HunyuanReconstructor | None = None,
) -> dict[str, Any]:
    backend = str(reconstruction["backend"])
    if backend == "primitive":
        mesh = _primitive_mesh(conditioning_image)
        source = "deterministic_primitive"
    elif backend == "hunyuan":
        session = reconstructor if reconstructor is not None else HunyuanReconstructor(reconstruction)
        mesh = session.reconstruct(conditioning_image, output)
        source = "Hunyuan3D-2.1"
    else:
        raise ValueError(f"unknown reconstruction backend: {backend}")
    return finalize_mesh(task_id, mesh, output, reconstruction, source)
