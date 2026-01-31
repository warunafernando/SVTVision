"""UVC/V4L2 camera discovery adapter."""

import os
import re
import subprocess
import json
from pathlib import Path
from typing import List, Dict, Any, Optional
from ..ports.camera_discovery_port import CameraDiscoveryPort
from ..services.logging_service import LoggingService


class UVCV4L2DiscoveryAdapter(CameraDiscoveryPort):
    """V4L2/UVC camera discovery adapter with deep hardware capabilities."""
    
    def __init__(self, logger: LoggingService):
        self.logger = logger
        self.video_devices_path = Path("/dev")
        self.usb_devices_path = Path("/sys/bus/usb/devices")
        
    def discover_cameras(self) -> List[Dict[str, Any]]:
        """Discover all V4L2 cameras, grouping by physical camera."""
        # Use v4l2-ctl --list-devices to group by physical camera
        physical_cameras = {}
        
        try:
            result = subprocess.run(
                ["v4l2-ctl", "--list-devices"],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            current_camera = None
            for line in result.stdout.split('\n'):
                line = line.strip()
                if not line:
                    continue
                
                # Check if this is a camera name line (doesn't start with /dev/)
                if not line.startswith('/dev/'):
                    # This is a camera name - extract physical identifier
                    current_camera = line
                    # Don't initialize here - only when we find a USB device
                elif line.startswith('/dev/video') and current_camera:
                    # This is a video device for the current camera
                    device_path = line.strip()
                    # Check if this is a USB camera (not platform device)
                    if self._is_usb_camera(device_path):
                        # Check if we already have this camera
                        if current_camera not in physical_cameras:
                            camera_id = self._get_stable_id(device_path)
                            if camera_id:
                                physical_cameras[current_camera] = {
                                    "id": camera_id,
                                    "name": self._extract_camera_name(current_camera),
                                    "device_path": device_path,
                                    "all_devices": [device_path],
                                    "available": True
                                }
                        else:
                            # Add to all_devices list
                            physical_cameras[current_camera]["all_devices"].append(device_path)
                    else:
                        # Skip non-USB cameras (platform devices)
                        self.logger.debug(f"[Discovery] Skipping non-USB camera: {device_path}")
                        current_camera = None  # Reset so we don't associate next device with this camera
        
        except Exception as e:
            self.logger.warning(f"[Discovery] Error using v4l2-ctl --list-devices: {e}")
            # Fallback to original method
            return self._discover_cameras_fallback()
        
        return list(physical_cameras.values())
    
    def _is_usb_camera(self, device_path: str) -> bool:
        """Check if camera is a USB camera (not platform device)."""
        try:
            result = subprocess.run(
                ["v4l2-ctl", "-d", device_path, "--info"],
                capture_output=True,
                text=True,
                timeout=2
            )
            # Check bus info - USB cameras have "usb-" in bus info
            for line in result.stdout.split('\n'):
                if 'Bus info' in line:
                    return 'usb-' in line.lower() or 'xhci' in line.lower()
            return False
        except Exception:
            return False
    
    def _discover_cameras_fallback(self) -> List[Dict[str, Any]]:
        """Fallback discovery method."""
        cameras = []
        video_devices = sorted(self.video_devices_path.glob("video*"))
        
        for video_dev in video_devices:
            try:
                # Only include USB cameras
                if self._is_usb_camera(str(video_dev)):
                    camera_id = self._get_stable_id(str(video_dev))
                    if camera_id:
                        cameras.append({
                            "id": camera_id,
                            "name": self._get_device_name(str(video_dev)),
                            "device_path": str(video_dev),
                            "all_devices": [str(video_dev)],
                            "available": True
                        })
            except Exception as e:
                self.logger.warning(f"[Discovery] Error discovering camera {video_dev}: {e}")
        
        return cameras
    
    def _extract_camera_name(self, device_line: str) -> str:
        """Extract camera name from v4l2-ctl output."""
        # Remove USB bus info in parentheses
        if '(' in device_line:
            name = device_line.split('(')[0].strip()
        else:
            name = device_line
        return name
    
    def get_camera_details(self, camera_id: str) -> Optional[Dict[str, Any]]:
        """Get full camera details."""
        device_path = self._id_to_device_path(camera_id)
        if not device_path:
            return None
        
        details = {
            "id": camera_id,
            "device_path": device_path,
            "name": self._get_device_name(device_path),
            "usb_info": self._get_usb_info(device_path),
            "kernel_info": self._get_kernel_info(device_path),
            "host_controller": self._get_host_controller(device_path),
        }
        
        return details
    
    def get_camera_capabilities(self, camera_id: str) -> Optional[Dict[str, Any]]:
        """Get camera capabilities."""
        device_path = self._id_to_device_path(camera_id)
        if not device_path:
            return None
        
        return {
            "formats": self._get_v4l2_formats(device_path),
            "resolutions": self._get_v4l2_resolutions(device_path),
            "fps_ranges": self._get_v4l2_fps_ranges(device_path),
        }
    
    def get_camera_controls(self, camera_id: str) -> Optional[List[Dict[str, Any]]]:
        """Get camera controls."""
        device_path = self._id_to_device_path(camera_id)
        if not device_path:
            return None
        
        return self._get_v4l2_controls(device_path)
    
    def _get_stable_id(self, device_path: str) -> Optional[str]:
        """Get stable camera ID (USB serial + bus/port, fallback to device path)."""
        # Try to get USB info for unique identification
        usb_info = self._get_usb_info(device_path)
        usb_serial = usb_info.get("serial")
        port_path = usb_info.get("port_path")
        
        if usb_serial:
            # If we have a port path, include it for uniqueness (same serial, different ports)
            if port_path:
                # Extract port identifier from port_path (e.g., "6-1" from "6-1:1.0")
                port_match = re.search(r'(\d+-\d+)', str(port_path))
                if port_match:
                    port_id = port_match.group(1)
                    return f"usb-{usb_serial}-{port_id}"
            return f"usb-{usb_serial}"
        
        # Fallback to device number
        match = re.search(r'video(\d+)', device_path)
        if match:
            return f"video{match.group(1)}"
        
        return None
    
    def _id_to_device_path(self, camera_id: str) -> Optional[str]:
        """Convert camera ID to device path."""
        if camera_id.startswith("video"):
            return f"/dev/{camera_id}"
        elif camera_id.startswith("usb-"):
            # Handle both formats: usb-SERIAL and usb-SERIAL-PORT
            # Extract port if present (pattern: -X-Y at the end where X and Y are digits)
            after_usb = camera_id[4:]  # Remove "usb-" prefix
            port_match = re.search(r'-(\d+-\d+)$', camera_id)
            
            if port_match:
                # New format: usb-SERIAL-PORT (e.g., usb-Arducam_202500915_0001-6-1)
                port_id = port_match.group(1)  # e.g., "6-1"
                # Extract serial by removing the -PORT suffix
                serial = after_usb[:len(after_usb)-len(port_id)-1]  # Remove -PORT
                return self._find_device_by_serial_and_port(serial, port_id)
            else:
                # Old format: usb-SERIAL
                return self._find_device_by_serial(after_usb)
        return None
    
    def _find_device_by_serial(self, serial: str) -> Optional[str]:
        """Find device path by USB serial number."""
        for video_dev in sorted(self.video_devices_path.glob("video*")):
            if not self._is_usb_camera(str(video_dev)):
                continue
            if self._get_usb_serial(str(video_dev)) == serial:
                return str(video_dev)
        return None
    
    def _find_device_by_serial_and_port(self, serial: str, port_id: str) -> Optional[str]:
        """Find device path by USB serial and port."""
        for video_dev in sorted(self.video_devices_path.glob("video*")):
            if not self._is_usb_camera(str(video_dev)):
                continue
            usb_info = self._get_usb_info(str(video_dev))
            device_serial = usb_info.get("serial")
            device_port = usb_info.get("port_path")
            if device_serial == serial and device_port == port_id:
                return str(video_dev)
        return None
    
    def _get_device_name(self, device_path: str) -> str:
        """Get device name using v4l2-ctl."""
        try:
            result = subprocess.run(
                ["v4l2-ctl", "-d", device_path, "--info"],
                capture_output=True,
                text=True,
                timeout=2
            )
            for line in result.stdout.split('\n'):
                if 'Card type' in line or 'Driver name' in line:
                    match = re.search(r':\s*(.+)', line)
                    if match:
                        return match.group(1).strip()
        except Exception as e:
            self.logger.debug(f"[Discovery] Error getting device name: {e}")
        
        return os.path.basename(device_path)
    
    def _get_usb_info(self, device_path: str) -> Dict[str, Any]:
        """Get USB device information."""
        info = {}
        
        try:
            # Find USB device in /sys
            sys_path = self._get_sys_path(device_path)
            if not sys_path:
                return info
            
            # Get USB device path
            usb_device_path = self._get_usb_device_path(sys_path)
            if not usb_device_path:
                return info
            
            usb_path = Path(usb_device_path)
            
            # VID/PID from udev or sysfs
            try:
                vid_file = usb_path / "idVendor"
                pid_file = usb_path / "idProduct"
                if vid_file.exists():
                    info["vid"] = vid_file.read_text().strip()
                if pid_file.exists():
                    info["pid"] = pid_file.read_text().strip()
            except Exception:
                # Fallback to parsing path
                vid_match = re.search(r'(\w{4}):(\w{4})', str(usb_device_path))
                if vid_match:
                    info["vid"] = vid_match.group(1)
                    info["pid"] = vid_match.group(2)
            
            # Serial number
            serial_path = usb_path / "serial"
            if serial_path.exists():
                info["serial"] = serial_path.read_text().strip()
            
            # Bus and port - extract from path
            # USB device path contains patterns like "6-1" which is bus-port
            parts = str(usb_device_path).split('/')
            for part in parts:
                # Look for USB device pattern (e.g., "6-1", "8-1") which is bus-port
                port_match = re.match(r'^(\d+)-(\d+)$', part)
                if port_match:
                    bus_num = port_match.group(1)
                    port_num = port_match.group(2)
                    info["port_path"] = part  # e.g., "6-1"
                    info["bus"] = bus_num
                    info["port"] = port_num
                    break  # Found the port identifier
                # Also look for patterns with colons (e.g., "6-1:1.0")
                if ':' in part and re.match(r'^\d+-\d+:', part):
                    port_match = re.match(r'^(\d+)-(\d+)', part)
                    if port_match:
                        bus_num = port_match.group(1)
                        port_num = port_match.group(2)
                        info["port_path"] = f"{bus_num}-{port_num}"  # Store just "6-1"
                        info["bus"] = bus_num
                        info["port"] = port_num
                        break
            
            # USB Version detection from speed
            speed_path = usb_path / "speed"
            if speed_path.exists():
                try:
                    speed_value = int(speed_path.read_text().strip())
                    info["negotiated_speed"] = str(speed_value)
                    # Determine USB version
                    if speed_value >= 5000:
                        info["usb_version"] = "USB3"
                    elif speed_value >= 480:
                        info["usb_version"] = "USB2"
                    else:
                        info["usb_version"] = "USB1"
                except (ValueError, AttributeError):
                    pass
            
            # Also check parent device for speed if not found
            if "usb_version" not in info:
                parent_speed = usb_path.parent / "speed"
                if parent_speed.exists():
                    try:
                        speed_value = int(parent_speed.read_text().strip())
                        if speed_value >= 5000:
                            info["usb_version"] = "USB3"
                        elif speed_value >= 480:
                            info["usb_version"] = "USB2"
                    except (ValueError, AttributeError):
                        pass
            
        except Exception as e:
            self.logger.debug(f"[Discovery] Error getting USB info: {e}")
        
        return info
    
    def _get_usb_serial(self, device_path: str) -> Optional[str]:
        """Get USB serial number."""
        usb_info = self._get_usb_info(device_path)
        return usb_info.get("serial")
    
    def _get_kernel_info(self, device_path: str) -> Dict[str, Any]:
        """Get kernel driver/module binding."""
        info = {}
        
        try:
            sys_path = self._get_sys_path(device_path)
            if not sys_path:
                return info
            
            # Driver
            driver_path = sys_path / "driver"
            if driver_path.exists():
                info["driver"] = driver_path.resolve().name
            
            # Module (from uevent)
            uevent_path = sys_path / "uevent"
            if uevent_path.exists():
                uevent_content = uevent_path.read_text()
                for line in uevent_content.split('\n'):
                    if line.startswith('DRIVER='):
                        info["driver"] = line.split('=', 1)[1]
                    elif 'MODALIAS' in line:
                        # Extract module info if available
                        pass
        
        except Exception as e:
            self.logger.debug(f"[Discovery] Error getting kernel info: {e}")
        
        return info
    
    def _get_host_controller(self, device_path: str) -> Dict[str, Any]:
        """Get host controller context (lspci entry)."""
        info = {}
        
        try:
            sys_path = self._get_sys_path(device_path)
            if not sys_path:
                return info
            
            usb_device_path = self._get_usb_device_path(sys_path)
            if not usb_device_path:
                return info
            
            # Get PCI bus info
            pci_path = Path(usb_device_path).parent
            while pci_path != Path('/'):
                if 'pci' in str(pci_path):
                    # Try to get lspci info
                    try:
                        result = subprocess.run(
                            ["lspci", "-v"],
                            capture_output=True,
                            text=True,
                            timeout=2
                        )
                        # Match USB controller
                        for line in result.stdout.split('\n'):
                            if 'USB' in line and 'controller' in line.lower():
                                info["lspci_entry"] = line.strip()
                                break
                    except Exception:
                        pass
                    break
                pci_path = pci_path.parent
        
        except Exception as e:
            self.logger.debug(f"[Discovery] Error getting host controller: {e}")
        
        return info
    
    def _get_v4l2_formats(self, device_path: str) -> List[str]:
        """Get supported V4L2 formats."""
        formats = []
        
        try:
            result = subprocess.run(
                ["v4l2-ctl", "-d", device_path, "--list-formats"],
                capture_output=True,
                text=True,
                timeout=2
            )
            for line in result.stdout.split('\n'):
                match = re.search(r"'([A-Z0-9_]+)'", line)
                if match:
                    formats.append(match.group(1))
        except Exception as e:
            self.logger.debug(f"[Discovery] Error getting formats: {e}")
        
        return formats
    
    def _get_v4l2_resolutions(self, device_path: str) -> List[Dict[str, Any]]:
        """Get supported resolutions for each format with FPS."""
        resolutions_by_format = {}
        
        try:
            result = subprocess.run(
                ["v4l2-ctl", "-d", device_path, "--list-formats-ext"],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            current_format = None
            current_resolution = None
            
            for line in result.stdout.split('\n'):
                line = line.strip()
                
                # Check for format line: [0]: 'YUYV' (YUYV 4:2:2)
                format_match = re.search(r"\[(\d+)\]:\s*'([A-Z0-9_]+)'", line)
                if format_match:
                    current_format = format_match.group(2)
                    if current_format not in resolutions_by_format:
                        resolutions_by_format[current_format] = []
                
                # Check for Size line: Size: Discrete 1920x1200
                size_match = re.search(r'Size:\s*(?:Discrete|Stepwise)\s*(\d+)x(\d+)', line)
                if size_match and current_format:
                    width = int(size_match.group(1))
                    height = int(size_match.group(2))
                    current_resolution = {
                        "width": width,
                        "height": height,
                        "fps": []
                    }
                    resolutions_by_format[current_format].append(current_resolution)
                
                # Check for Interval line: Interval: Discrete 0.020s (50.000 fps)
                if current_resolution and 'Interval' in line:
                    fps_match = re.search(r'\((\d+(?:\.\d+)?)\s*fps\)', line)
                    if fps_match:
                        fps_value = float(fps_match.group(1))
                        if fps_value not in current_resolution["fps"]:
                            current_resolution["fps"].append(fps_value)
        
        except Exception as e:
            self.logger.debug(f"[Discovery] Error getting resolutions: {e}")
        
        # Convert to expected format
        result_list = []
        for fmt, resolutions in list(resolutions_by_format.items())[:3]:  # Limit formats
            # Sort resolutions by area (width * height)
            sorted_res = sorted(resolutions, key=lambda x: x["width"] * x["height"], reverse=True)
            result_list.append({
                "format": fmt,
                "resolutions": sorted_res[:20]  # Limit to 20 resolutions per format
            })
        
        return result_list
    
    def _get_v4l2_fps_ranges(self, device_path: str) -> List[Dict[str, Any]]:
        """Get FPS ranges per format/resolution combination."""
        fps_ranges = []
        
        try:
            resolutions = self._get_v4l2_resolutions(device_path)
            for fmt_info in resolutions:
                format_name = fmt_info["format"]
                for res in fmt_info["resolutions"]:
                    if res["fps"]:
                        fps_ranges.append({
                            "format": format_name,
                            "width": res["width"],
                            "height": res["height"],
                            "fps": sorted(res["fps"]),
                            "min_fps": min(res["fps"]),
                            "max_fps": max(res["fps"])
                        })
        except Exception as e:
            self.logger.debug(f"[Discovery] Error getting FPS ranges: {e}")
        
        return fps_ranges[:50]  # Limit results
    
    def _get_v4l2_controls(self, device_path: str) -> List[Dict[str, Any]]:
        """Get V4L2 controls."""
        controls = []
        
        try:
            result = subprocess.run(
                ["v4l2-ctl", "-d", device_path, "--list-ctrls"],
                capture_output=True,
                text=True,
                timeout=2
            )
            for line in result.stdout.split('\n'):
                if ':' in line:
                    parts = line.split(':', 1)
                    name = parts[0].strip()
                    value_part = parts[1].strip() if len(parts) > 1 else ""
                    
                    # Parse value, min, max, step, default
                    control = {"name": name}
                    
                    # Extract numeric values
                    numbers = re.findall(r'(\d+(?:\.\d+)?)', value_part)
                    if numbers:
                        control["current"] = float(numbers[0]) if '.' in numbers[0] else int(numbers[0])
                    
                    # Look for min/max/step/default keywords
                    if 'min' in value_part.lower():
                        match = re.search(r'min[=:]?\s*(\d+(?:\.\d+)?)', value_part, re.IGNORECASE)
                        if match:
                            val = match.group(1)
                            control["min"] = float(val) if '.' in val else int(val)
                    
                    if 'max' in value_part.lower():
                        match = re.search(r'max[=:]?\s*(\d+(?:\.\d+)?)', value_part, re.IGNORECASE)
                        if match:
                            val = match.group(1)
                            control["max"] = float(val) if '.' in val else int(val)
                    
                    if 'step' in value_part.lower():
                        match = re.search(r'step[=:]?\s*(\d+(?:\.\d+)?)', value_part, re.IGNORECASE)
                        if match:
                            val = match.group(1)
                            control["step"] = float(val) if '.' in val else int(val)
                    
                    if 'default' in value_part.lower():
                        match = re.search(r'default[=:]?\s*(\d+(?:\.\d+)?)', value_part, re.IGNORECASE)
                        if match:
                            val = match.group(1)
                            control["default"] = float(val) if '.' in val else int(val)
                    
                    controls.append(control)
        except Exception as e:
            self.logger.debug(f"[Discovery] Error getting controls: {e}")
        
        return controls
    
    def _get_sys_path(self, device_path: str) -> Optional[Path]:
        """Get sysfs path for device."""
        try:
            # Direct symlink resolution
            dev_name = os.path.basename(device_path)
            sys_link = Path(f"/sys/class/video4linux/{dev_name}")
            if sys_link.exists():
                # Resolve to real path
                real_path = sys_link.resolve()
                return real_path
        except Exception as e:
            self.logger.debug(f"[Discovery] Error getting sys path: {e}")
        
        return None
    
    def _get_usb_device_path(self, sys_path: Path) -> Optional[str]:
        """Get USB device path from sys path."""
        try:
            # Walk up the path to find USB device directory
            # USB device directories are typically named like "6-1", "8-1", etc.
            # They contain idVendor, idProduct, and speed files
            current = sys_path
            for _ in range(20):  # Limit depth
                # Check if this directory has USB device files (idVendor, idProduct)
                if (current / "idVendor").exists() and (current / "idProduct").exists():
                    return str(current)
                
                # Also check parent if current matches USB device pattern (e.g., "6-1", "8-1")
                if re.match(r'^\d+-\d+$', current.name):
                    # Check if parent has the USB device files, or if current has them
                    if (current / "idVendor").exists():
                        return str(current)
                    if (current.parent / "idVendor").exists():
                        return str(current.parent)
                
                # Check for speed file - if found, check for idVendor/idProduct nearby
                if (current / "speed").exists():
                    # Check parent and siblings for USB device files
                    if (current / "idVendor").exists():
                        return str(current)
                    if (current.parent / "idVendor").exists():
                        return str(current.parent)
                
                current = current.parent
                if current == Path('/'):
                    break
        except Exception as e:
            self.logger.debug(f"[Discovery] Error finding USB device path: {e}")
        
        return None
