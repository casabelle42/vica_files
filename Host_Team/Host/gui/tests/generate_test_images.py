#!/usr/bin/env python3
"""
Generate Test Images for LAS-VICA Query Testing
================================================

Creates synthetic images depicting people standing behind a black car
for testing the query: "is there anyone behind the black car"

These images are used by the mock server to return realistic responses.
"""

import os
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import random

# Output directory
SCRIPT_DIR = Path(__file__).parent
TEST_IMAGES_DIR = SCRIPT_DIR / "test_images"


def create_scene_background(width: int = 800, height: int = 600) -> Image.Image:
    """Create a simple outdoor scene background."""
    img = Image.new("RGB", (width, height))
    draw = ImageDraw.Draw(img)
    
    # Sky gradient (light blue to darker blue)
    for y in range(height // 2):
        ratio = y / (height // 2)
        r = int(135 + (200 - 135) * (1 - ratio))
        g = int(206 + (230 - 206) * (1 - ratio))
        b = int(235 + (255 - 235) * (1 - ratio))
        draw.line([(0, y), (width, y)], fill=(r, g, b))
    
    # Ground (gray pavement)
    for y in range(height // 2, height):
        ratio = (y - height // 2) / (height // 2)
        gray = int(120 - 30 * ratio)
        draw.line([(0, y), (width, y)], fill=(gray, gray, gray))
    
    return img


def draw_black_car(img: Image.Image, x: int, y: int, scale: float = 1.0) -> Image.Image:
    """Draw a simple black car silhouette."""
    draw = ImageDraw.Draw(img)
    
    # Car dimensions
    car_width = int(280 * scale)
    car_height = int(100 * scale)
    roof_height = int(60 * scale)
    wheel_radius = int(25 * scale)
    
    # Car body (black rectangle with rounded appearance)
    body_rect = [x, y, x + car_width, y + car_height]
    draw.rounded_rectangle(body_rect, radius=int(15 * scale), fill=(20, 20, 25))
    
    # Car roof
    roof_rect = [
        x + int(50 * scale), 
        y - roof_height, 
        x + car_width - int(60 * scale), 
        y + int(10 * scale)
    ]
    draw.rounded_rectangle(roof_rect, radius=int(20 * scale), fill=(25, 25, 30))
    
    # Windows (dark blue tint)
    window_rect = [
        x + int(60 * scale),
        y - roof_height + int(10 * scale),
        x + car_width - int(70 * scale),
        y
    ]
    draw.rounded_rectangle(window_rect, radius=int(10 * scale), fill=(30, 40, 60))
    
    # Wheels
    wheel1_center = (x + int(60 * scale), y + car_height - int(5 * scale))
    wheel2_center = (x + car_width - int(60 * scale), y + car_height - int(5 * scale))
    
    for center in [wheel1_center, wheel2_center]:
        draw.ellipse([
            center[0] - wheel_radius, center[1] - wheel_radius,
            center[0] + wheel_radius, center[1] + wheel_radius
        ], fill=(15, 15, 15))
        # Wheel rim
        draw.ellipse([
            center[0] - int(wheel_radius * 0.5), center[1] - int(wheel_radius * 0.5),
            center[0] + int(wheel_radius * 0.5), center[1] + int(wheel_radius * 0.5)
        ], fill=(80, 80, 85))
    
    # Headlights and taillights
    draw.ellipse([x + int(5 * scale), y + int(20 * scale), 
                  x + int(25 * scale), y + int(40 * scale)], fill=(255, 255, 200))
    draw.ellipse([x + car_width - int(25 * scale), y + int(20 * scale),
                  x + car_width - int(5 * scale), y + int(40 * scale)], fill=(255, 50, 50))
    
    return img


def draw_person(img: Image.Image, x: int, y: int, scale: float = 1.0, 
                shirt_color: tuple = (200, 50, 50)) -> Image.Image:
    """Draw a simple person silhouette."""
    draw = ImageDraw.Draw(img)
    
    # Person dimensions
    head_radius = int(20 * scale)
    body_height = int(80 * scale)
    body_width = int(40 * scale)
    leg_height = int(60 * scale)
    
    # Legs (pants - dark blue/black)
    pants_color = (40, 45, 60)
    leg_width = int(15 * scale)
    # Left leg
    draw.rectangle([
        x - int(12 * scale), y + body_height,
        x - int(12 * scale) + leg_width, y + body_height + leg_height
    ], fill=pants_color)
    # Right leg
    draw.rectangle([
        x + int(12 * scale) - leg_width, y + body_height,
        x + int(12 * scale), y + body_height + leg_height
    ], fill=pants_color)
    
    # Body (shirt)
    body_rect = [
        x - body_width // 2, y,
        x + body_width // 2, y + body_height
    ]
    draw.rounded_rectangle(body_rect, radius=int(10 * scale), fill=shirt_color)
    
    # Arms
    arm_width = int(12 * scale)
    arm_length = int(50 * scale)
    # Left arm
    draw.rounded_rectangle([
        x - body_width // 2 - arm_width, y + int(10 * scale),
        x - body_width // 2, y + int(10 * scale) + arm_length
    ], radius=int(5 * scale), fill=shirt_color)
    # Right arm
    draw.rounded_rectangle([
        x + body_width // 2, y + int(10 * scale),
        x + body_width // 2 + arm_width, y + int(10 * scale) + arm_length
    ], radius=int(5 * scale), fill=shirt_color)
    
    # Head (skin tone)
    skin_color = (220, 185, 155)
    draw.ellipse([
        x - head_radius, y - head_radius * 2,
        x + head_radius, y
    ], fill=skin_color)
    
    # Hair
    hair_color = (50, 35, 25)
    draw.arc([
        x - head_radius, y - head_radius * 2,
        x + head_radius, y - head_radius
    ], start=180, end=360, fill=hair_color, width=int(8 * scale))
    
    return img


def generate_test_image(
    image_id: int,
    num_people: int = 2,
    width: int = 800,
    height: int = 600,
    camera_name: str = "Edge-Cam-01",
    box_car: bool = False,
    box_people: bool = True
) -> Image.Image:
    """Generate a test image with people behind a black car.
    
    Args:
        image_id: Unique image ID for timestamp
        num_people: Number of people to draw
        width, height: Image dimensions
        camera_name: Camera identifier for overlay
        box_car: Whether to draw bounding box around car
        box_people: Whether to draw bounding boxes around people
    """
    
    # Create background
    img = create_scene_background(width, height)
    
    # Draw people (positioned behind where the car will be)
    person_y_base = height // 2 - 50  # Above the ground line
    shirt_colors = [
        (200, 50, 50),   # Red
        (50, 100, 200),  # Blue
        (50, 180, 80),   # Green
        (220, 180, 50),  # Yellow
        (150, 50, 180),  # Purple
    ]
    
    # Position people behind the car
    car_x = width // 2 - 140
    car_y = height // 2 + 20
    
    for i in range(num_people):
        # People positioned behind and slightly above the car
        person_x = car_x + 100 + i * 80 + random.randint(-20, 20)
        person_y = person_y_base - 80 + random.randint(-10, 10)
        scale = 0.8 + random.random() * 0.3
        shirt = shirt_colors[i % len(shirt_colors)]
        img = draw_person(img, person_x, person_y, scale=scale, shirt_color=shirt)
    
    # Draw the black car in front
    img = draw_black_car(img, car_x, car_y, scale=1.0)
    
    # Add detection bounding boxes (simulating AI detection)
    draw = ImageDraw.Draw(img)
    
    try:
        font = ImageFont.truetype("arial.ttf", 14)
    except:
        font = ImageFont.load_default()
    
    # Draw bounding box around car if requested
    if box_car:
        car_width = 280
        car_height = 100
        roof_height = 60
        box_padding = 15
        draw.rectangle([
            car_x - box_padding,
            car_y - roof_height - box_padding,
            car_x + car_width + box_padding,
            car_y + car_height + box_padding
        ], outline=(255, 165, 0), width=3)  # Orange for car
        
        # Car label
        car_confidence = 0.95 + random.random() * 0.04
        car_label = f"car {car_confidence:.0%}"
        draw.rectangle([
            car_x - box_padding,
            car_y - roof_height - box_padding - 22,
            car_x + 70,
            car_y - roof_height - box_padding
        ], fill=(255, 165, 0))
        draw.text(
            (car_x - box_padding + 3, car_y - roof_height - box_padding - 20),
            car_label,
            fill=(0, 0, 0),
            font=font
        )
    
    # Draw bounding boxes around detected people
    if box_people:
        for i in range(num_people):
            person_x = car_x + 100 + i * 80
            person_y = person_y_base - 80
            
            # Bounding box
            box_padding = 10
            draw.rectangle([
                person_x - 30 - box_padding,
                person_y - 45 - box_padding,
                person_x + 30 + box_padding,
                person_y + 140 + box_padding
            ], outline=(0, 255, 0), width=2)
            
            confidence = 0.85 + random.random() * 0.14
            label = f"person {confidence:.0%}"
            draw.rectangle([
                person_x - 30 - box_padding,
                person_y - 65,
                person_x + 50,
                person_y - 45 - box_padding
            ], fill=(0, 255, 0))
            draw.text(
                (person_x - 28, person_y - 63),
                label,
                fill=(0, 0, 0),
                font=font
            )
    
    # Add metadata overlay with camera name
    try:
        font = ImageFont.truetype("arial.ttf", 12)
    except:
        font = ImageFont.load_default()
    
    timestamp = f"2026-02-05 19:30:{10 + image_id:02d}"
    draw.rectangle([5, 5, 220, 25], fill=(0, 0, 0, 180))
    draw.text((10, 8), f"{camera_name} | {timestamp}", fill=(255, 255, 255), font=font)
    
    return img


def main():
    """Generate all test images."""
    TEST_IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    
    print("Generating test images for LAS-VICA query testing...")
    
    # Camera names
    cameras = ["Edge-Cam-01", "Edge-Cam-02", "Edge-Cam-03"]
    
    # Standard person detection images (for each camera)
    print("\n[1] Generating person detection images (all cameras)...")
    for cam_idx, camera in enumerate(cameras):
        for person_count in [1, 2, 3]:
            img = generate_test_image(
                image_id=cam_idx * 3 + person_count,
                num_people=person_count,
                camera_name=camera,
                box_car=False,
                box_people=True
            )
            filename = f"{camera.lower().replace('-', '_')}_person_{person_count:02d}.jpg"
            filepath = TEST_IMAGES_DIR / filename
            img.save(filepath, "JPEG", quality=90)
            print(f"  [OK] {filename}")
    
    # Car detection images (with car bounding boxes)
    print("\n[2] Generating car detection images...")
    for cam_idx, camera in enumerate(cameras[:2]):  # 2 cameras for car
        img = generate_test_image(
            image_id=10 + cam_idx,
            num_people=1,
            camera_name=camera,
            box_car=True,
            box_people=False
        )
        filename = f"{camera.lower().replace('-', '_')}_car.jpg"
        filepath = TEST_IMAGES_DIR / filename
        img.save(filepath, "JPEG", quality=90)
        print(f"  [OK] {filename}")
    
    # Combined car + person detection
    print("\n[3] Generating combined detection images...")
    for cam_idx, camera in enumerate(cameras):
        img = generate_test_image(
            image_id=20 + cam_idx,
            num_people=2,
            camera_name=camera,
            box_car=True,
            box_people=True
        )
        filename = f"{camera.lower().replace('-', '_')}_combined.jpg"
        filepath = TEST_IMAGES_DIR / filename
        img.save(filepath, "JPEG", quality=90)
        print(f"  [OK] {filename}")
    
    # Legacy filenames for backward compatibility
    print("\n[4] Generating legacy format images...")
    configs = [
        {"image_id": 1, "num_people": 1},
        {"image_id": 2, "num_people": 2},
        {"image_id": 3, "num_people": 3},
        {"image_id": 4, "num_people": 2},
        {"image_id": 5, "num_people": 1},
    ]
    
    for config in configs:
        img = generate_test_image(**config, camera_name="Edge-Cam-01", box_people=True)
        filename = f"person_behind_car_{config['image_id']:02d}.jpg"
        filepath = TEST_IMAGES_DIR / filename
        img.save(filepath, "JPEG", quality=90)
        print(f"  [OK] {filename}")
    
    print(f"\nGenerated test images in: {TEST_IMAGES_DIR}")


if __name__ == "__main__":
    main()
