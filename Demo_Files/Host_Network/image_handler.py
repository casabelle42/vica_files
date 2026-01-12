"""
Image Handler Module for Sentinel Nexus V2

Handles processing of incoming image messages from edge devices.
Decodes base64 image data and dispatches it to registered callbacks.
"""

import base64
import logging
from typing import Dict, Any, Optional, Callable
from dataclasses import dataclass

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class ReceivedImage:
    """Represents a received image from an edge device."""
    image_id: str
    image_bytes: bytes
    image_format: str
    width: int
    height: int
    timestamp: float
    device_id: str = ""


class ImageHandler:
    """
    Handles processing of incoming image messages from edge devices.
    Decodes base64 image data and dispatches it to registered callbacks.
    """
    
    def __init__(self, image_received_callback: Optional[Callable[[ReceivedImage], None]] = None):
        """
        Initialize image handler.
        
        Args:
            image_received_callback: Callback function to handle received images
        """
        self.image_received_callback = image_received_callback
        self.processed_images = 0
        logger.info("ImageHandler initialized")
    
    def handle_image_message(self, message: Any) -> Optional[ReceivedImage]:
        """
        Process an incoming image message from edge device.
        Handles JPEG bytes from edge device's image_data format.
        
        Args:
            message: NetworkMessage containing image data
            
        Returns:
            ReceivedImage object if successful, None otherwise
        """
        try:
            # Extract image data from message (edge device format)
            image_data = message.data
            image_id = image_data.get('image_id', f'image_{int(message.timestamp)}')
            image_data_b64 = image_data.get('image_data', '')
            # Edge device sends 'format' field, default to JPEG for edge device
            image_format = image_data.get('format', 'JPEG')
            image_width = image_data.get('width', 0)
            image_height = image_data.get('height', 0)
            device_id = message.device_id if hasattr(message, 'device_id') else 'unknown'
            query_id = image_data.get('query_id')
            
            logger.info(f"Processing image message: {image_id}, format: {image_format}, size: {image_width}x{image_height}")
            
            if not image_data_b64:
                logger.warning(f"Received image message with no base64 data for image_id: {image_id}")
                return None
            
            # THIS IS WHERE IMAGE IS DECODED
            # Decode base64 image data
            image_bytes = base64.b64decode(image_data_b64)
            logger.info(f"Decoded image {image_id} ({len(image_bytes)} bytes) from base64")
            
            # Create ReceivedImage object with JPEG bytes from edge device
            received_image = ReceivedImage(
                image_id=image_id,
                image_bytes=image_bytes,  # These are JPEG bytes from edge device
                image_format='JPEG',      # Edge device sends JPEG format
                width=image_width,
                height=image_height,
                timestamp=message.timestamp,
                device_id=device_id
            )
            
            # Call the registered callback with the processed image
            if self.image_received_callback:
                try:
                    self.image_received_callback(received_image)
                    self.processed_images += 1
                    logger.info(f"Image {image_id} dispatched to callback (total processed: {self.processed_images})")
                except Exception as e:
                    logger.error(f"Error in image callback: {e}")
            else:
                logger.warning("No image_received_callback registered in ImageHandler")
            
            return received_image
            
        except base64.binascii.Error as e:
            logger.error(f"Base64 decoding error for image {image_id}: {e}")
            return None
        except Exception as e:
            logger.error(f"Error handling image message: {e}", exc_info=True)
            return None
    
    def register_callback(self, callback: Callable[[ReceivedImage], None]):
        """
        Register a callback function for received images.
        
        Args:
            callback: Function to call when an image is received
        """
        self.image_received_callback = callback
        logger.info("Image callback registered")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get handler statistics."""
        return {
            "processed_images": self.processed_images,
            "has_callback": self.image_received_callback is not None
        }


# Example usage and testing
if __name__ == "__main__":
    # Create image handler with callback
    def image_callback(received_image: ReceivedImage):
        print(f"Received image: {received_image.image_id}")
        print(f"  Size: {received_image.width}x{received_image.height}")
        print(f"  Format: {received_image.image_format}")
        print(f"  Data size: {len(received_image.image_bytes)} bytes")
        print(f"  Device: {received_image.device_id}")
    
    handler = ImageHandler(image_callback)
    
    # Simulate receiving an image message
    class MockMessage:
        def __init__(self):
            self.timestamp = 1234567890.123
            self.data = {
                'image_id': 'test_image_001',
                'image_data': base64.b64encode(b'mock_image_data').decode('utf-8'),
                'image_format': 'RGB',
                'width': 640,
                'height': 480,
                'device_id': 'edge_device_001'
            }
    
    # Test the handler
    mock_message = MockMessage()
    result = handler.handle_image_message(mock_message)
    
    if result:
        print("✅ Image handler test passed")
    else:
        print("❌ Image handler test failed")
    
    # Show stats
    stats = handler.get_stats()
    print(f"Handler stats: {stats}")
