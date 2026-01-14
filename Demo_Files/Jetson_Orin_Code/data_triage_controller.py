#!/usr/bin/env python3
"""
Data Triage Controller
Manages image capture and inclusion in query responses for testing.
This is the initial simple implementation before full triage logic.
"""

import logging
import time
from typing import Optional, Dict, Any
from frame_capture import FrameCapture

logger = logging.getLogger(__name__)


class DataTriageController:
    """Controls data triage functionality - captures and includes images in responses"""

    def __init__(self, video_source: int = 0, width: int = 1280, height: int = 720, jpeg_quality: int = 85):
        """
        Initialize data triage controller

        Args:
            video_source: Camera device index
            width: Frame width
            height: Frame height
            jpeg_quality: JPEG compression quality (1-100)
        """
        self.enabled = False
        self.video_source = video_source
        self.width = width
        self.height = height
        self.jpeg_quality = jpeg_quality

        # Initialize frame capture (but don't open camera yet - lazy initialization)
        self.frame_capture = FrameCapture(video_source, width, height)
        # Don't initialize camera at startup - will initialize on first capture
        # This allows other processes (like VILA) to start first

        # Statistics
        self.stats = {
            'frames_captured': 0,
            'frames_sent': 0,
            'capture_errors': 0,
            'encode_errors': 0
        }

        logger.info(
            f"DataTriageController initialized (video_source={video_source}, {width}x{height})")

    def enable(self):
        """Enable image triage"""
        if not self.enabled:
            self.enabled = True
            logger.info(
                "Data triage enabled - images will be included in query responses")
        else:
            logger.info("Data triage already enabled")

    def disable(self):
        """Disable image triage"""
        if self.enabled:
            self.enabled = False
            logger.info("Data triage disabled")
        else:
            logger.info("Data triage already disabled")

    def capture_image_for_query(self, query_text: str = "") -> Optional[Dict[str, Any]]:
        """
        Capture an image for the current query

        Args:
            query_text: The query text (for logging/metadata)

        Returns:
            Dictionary with image data or None if capture failed
        """
        if not self.enabled:
            logger.debug("Data triage disabled, skipping image capture")
            return None

        try:
            logger.info(f"Capturing image for query: {query_text[:50]}...")

            # Check if camera is initialized
            if not self.frame_capture.is_initialized():
                logger.warning(
                    "Camera not initialized, attempting to initialize...")
                if not self.frame_capture.initialize():
                    logger.warning(
                        "Failed to initialize camera, skipping image capture")
                    self.stats['capture_errors'] += 1
                    return None

            # Capture and encode frame
            result = self.frame_capture.capture_and_encode(self.jpeg_quality)

            if result is None:
                logger.warning(
                    "Failed to capture frame for query (capture_and_encode returned None)")
                self.stats['capture_errors'] += 1
                return None

            jpeg_bytes, timestamp, width, height = result
            self.stats['frames_captured'] += 1

            # Create image data dictionary
            image_data = {
                'jpeg_bytes': jpeg_bytes,
                'timestamp': timestamp,
                'width': width,
                'height': height,
                'format': 'JPEG',
                'quality': self.jpeg_quality,
                'size_bytes': len(jpeg_bytes),
                'query_text': query_text
            }

            self.stats['frames_sent'] += 1
            logger.info(
                f"Captured image: {width}x{height}, {len(jpeg_bytes)} bytes")

            return image_data

        except Exception as e:
            logger.error(
                f"Error capturing image for query: {e}", exc_info=True)
            self.stats['capture_errors'] += 1
            return None

    def get_stats(self) -> Dict[str, Any]:
        """Get triage statistics"""
        return {
            **self.stats,
            'enabled': self.enabled,
            'camera_initialized': self.frame_capture.is_initialized()
        }

    def reset_stats(self):
        """Reset statistics"""
        self.stats = {
            'frames_captured': 0,
            'frames_sent': 0,
            'capture_errors': 0,
            'encode_errors': 0
        }
        logger.info("Triage statistics reset")

    def cleanup(self):
        """Cleanup resources"""
        logger.info("Cleaning up DataTriageController...")
        self.frame_capture.release()
        self.enabled = False
