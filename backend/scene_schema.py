"""Validated, portable contract between photo analysis, Blender, and the viewer.

Coordinates are metres (estimated), Y up, with the photographed back wall at -Z.
Object positions are box centres; fronts point local +Z before rotation_y.
"""

from __future__ import annotations

import math
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Vec2 = tuple[float, float]
Vec3 = tuple[float, float, float]
Positive = Annotated[float, Field(gt=0, le=100)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Material(StrictModel):
    color: Vec3 = (0.7, 0.7, 0.7)
    roughness: float = Field(default=0.65, ge=0, le=1)
    metalness: float = Field(default=0, ge=0, le=1)
    kind: str = "paint"
    texture: str | None = None
    texture_tile_size: Positive = 1
    texture_repeat: bool = True

    @model_validator(mode="after")
    def safe_texture(self):
        if any(v < 0 or v > 1 for v in self.color):
            raise ValueError("Material color channels must be between zero and one")
        if self.texture and (self.texture.startswith(("/", "\\")) or ".." in self.texture.replace("\\", "/").split("/")):
            raise ValueError("Texture paths must stay within the project directory")
        return self


class Opening(StrictModel):
    kind: Literal["door", "window", "opening"] = "opening"
    offset: float = Field(ge=0)
    width: Positive
    height: Positive
    bottom: float = Field(default=0, ge=0)
    confidence: float = Field(default=0.5, ge=0, le=1)
    material: str | None = None


class Wall(StrictModel):
    id: str
    start: Vec2
    end: Vec2
    height: Positive
    thickness: float = Field(default=0.12, gt=0, le=1)
    material: str = "wall"
    openings: list[Opening] = Field(default_factory=list)

    @model_validator(mode="after")
    def opening_bounds(self):
        length = math.dist(self.start, self.end)
        if length < 0.2:
            raise ValueError("Wall must have nonzero length")
        for opening in self.openings:
            if opening.offset + opening.width > length + 0.03 or opening.bottom + opening.height > self.height + 0.03:
                raise ValueError("Opening must fit inside its wall")
        return self


class Room(StrictModel):
    width: Positive
    depth: Positive
    height: Positive
    floor_polygon: list[Vec2] = Field(min_length=3, max_length=24)
    walls: list[Wall] = Field(min_length=1, max_length=24)
    ceiling: bool = True
    floor_material: str = "floor"
    ceiling_material: str = "ceiling"


class Camera(StrictModel):
    position: Vec3
    target: Vec3
    fov: float = Field(default=55, ge=15, le=115)
    aspect: float = Field(default=1.5, gt=0, le=8)
    fov_axis: Literal["vertical", "horizontal"] = "vertical"


class WalkStart(StrictModel):
    position: Vec3
    target: Vec3


class SceneObject(StrictModel):
    id: str
    kind: Literal["cabinet", "slat_wall", "workbench", "shelf", "box"]
    position: Vec3
    dimensions: tuple[Positive, Positive, Positive]
    rotation_y: float = 0
    wall_id: str | None = None
    material: str = "object"
    front_material: str | None = None
    confidence: float = Field(default=0.5, ge=0, le=1)


class Source(StrictModel):
    image_path: str
    width: int = Field(gt=0, le=24000)
    height: int = Field(gt=0, le=24000)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class Analysis(StrictModel):
    confidence: float = Field(ge=0, le=1)
    warnings: list[str] = Field(default_factory=list)
    method: str
    diagnostics: dict = Field(default_factory=dict)


class SceneDescriptor(StrictModel):
    schema_version: Literal[1] = 1
    units: Literal["estimated_meters"] = "estimated_meters"
    room: Room
    camera: Camera
    walk_start: WalkStart
    objects: list[SceneObject] = Field(default_factory=list, max_length=100)
    materials: dict[str, Material]
    source: Source
    analysis: Analysis

    @model_validator(mode="after")
    def references(self):
        wall_ids = {wall.id for wall in self.room.walls}
        refs = [self.room.floor_material, self.room.ceiling_material]
        refs.extend(wall.material for wall in self.room.walls)
        refs.extend(opening.material for wall in self.room.walls for opening in wall.openings if opening.material)
        for obj in self.objects:
            if obj.wall_id and obj.wall_id not in wall_ids:
                raise ValueError("Object refers to an unknown wall")
            refs.append(obj.material)
            if obj.front_material:
                refs.append(obj.front_material)
        if any(ref not in self.materials for ref in refs):
            raise ValueError("Scene refers to an unknown material")
        return self


def validate_scene(value: dict) -> dict:
    """Validate corrected scenes and return the plain JSON-serializable shape."""
    return SceneDescriptor.model_validate(value).model_dump(mode="json")
