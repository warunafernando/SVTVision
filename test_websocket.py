#!/usr/bin/env python3
"""Test WebSocket connection to verify streaming works."""

import asyncio
import websockets
import json
import sys

async def test_websocket():
    """Test WebSocket connection to camera stream."""
    # Get camera ID from command line or use first available
    camera_id = sys.argv[1] if len(sys.argv) > 1 else None
    
    if not camera_id:
        # Try to get first camera from API
        import urllib.request
        try:
            with urllib.request.urlopen('http://localhost:8080/api/cameras') as response:
                data = json.loads(response.read())
                cameras = data.get('cameras', [])
                if cameras:
                    camera_id = cameras[0]['id']
                    print(f"Using first camera: {camera_id}")
                else:
                    print("ERROR: No cameras available")
                    return
        except Exception as e:
            print(f"ERROR: Cannot fetch cameras: {e}")
            return
    
    uri = f"ws://localhost:8080/ws/stream?camera={camera_id}&stage=raw"
    print(f"Connecting to: {uri}")
    
    try:
        async with websockets.connect(uri) as websocket:
            print("✓ WebSocket connected!")
            frame_count = 0
            no_frame_count = 0
            
            while True:
                try:
                    message = await asyncio.wait_for(websocket.recv(), timeout=2.0)
                    data = json.loads(message)
                    
                    if data.get('type') == 'frame':
                        frame_count += 1
                        frame_size = len(data.get('data', ''))
                        metrics = data.get('metrics', {})
                        fps = metrics.get('fps', 0)
                        drops = metrics.get('drops', 0)
                        
                        if frame_count % 30 == 0:  # Log every 30 frames
                            print(f"  Frames received: {frame_count}, Size: {frame_size} bytes, FPS: {fps}, Drops: {drops}")
                    elif data.get('type') == 'no_frame':
                        no_frame_count += 1
                        if no_frame_count % 10 == 0:
                            print(f"  No frame messages: {no_frame_count}")
                    else:
                        print(f"  Unexpected message type: {data.get('type')}")
                        
                except asyncio.TimeoutError:
                    print("  ⚠ Timeout waiting for message")
                    break
                except Exception as e:
                    print(f"  ERROR: {e}")
                    break
                    
            print(f"\nTotal frames received: {frame_count}")
            print(f"Total no_frame messages: {no_frame_count}")
            
    except Exception as e:
        print(f"ERROR connecting to WebSocket: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_websocket())
