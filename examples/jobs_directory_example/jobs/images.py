"""
Image processing background jobs
"""

import asyncio

import fastjob


@fastjob.job(queue="media")
async def resize_image(image_path: str, width: int, height: int):
    """Resize an uploaded image."""
    print(f"🖼️  Resizing image {image_path} to {width}x{height}")
    await asyncio.sleep(2)  # Simulate image processing
    print(f"✅ Image resized: {image_path}")


@fastjob.job(queue="media", retries=2)
async def generate_thumbnails(image_path: str, sizes: list[tuple[int, int]]):
    """Generate multiple thumbnail sizes for an image."""
    print(f"📷 Generating thumbnails for {image_path}")

    for width, height in sizes:
        print(f"  → Creating {width}x{height} thumbnail")
        await asyncio.sleep(0.5)  # Simulate thumbnail generation

    print(f"✅ Generated {len(sizes)} thumbnails for {image_path}")


@fastjob.job(queue="media", priority=10)  # Lower priority for batch operations
async def batch_optimize_images(image_paths: list[str]):
    """Optimize multiple images for web delivery."""
    print(f"⚡ Batch optimizing {len(image_paths)} images")

    for image_path in image_paths:
        print(f"  → Optimizing {image_path}")
        await asyncio.sleep(1)  # Simulate optimization

    print(f"✅ Optimized {len(image_paths)} images for web")
