import subprocess
import os
import logging
from config import FFMPEG_PRESET, FFMPEG_CRF

logger = logging.getLogger(__name__)

class Merger:
    def __init__(self):
        pass

    def merge_videos(self, video_files, output_file, mode="fast"):
        """Merge multiple video files into one using FFmpeg"""
        if not video_files:
            return False

        # Create a list file for ffmpeg concat
        list_file = "concat_list.txt"
        with open(list_file, "w", encoding="utf-8") as f:
            for video in video_files:
                # Use absolute path and escape single quotes for ffmpeg
                abs_path = os.path.abspath(video).replace("'", "'\\''")
                f.write(f"file '{abs_path}'\n")

        try:
            if mode == "fast":
                # Fast Merge (copy codec)
                command = [
                    'ffmpeg', '-y', '-f', 'concat', '-safe', '0', '-i', list_file,
                    '-c', 'copy', output_file
                ]
            else:
                # Re-encode fallback
                command = [
                    'ffmpeg', '-y', '-f', 'concat', '-safe', '0', '-i', list_file,
                    '-vcodec', 'libx264', '-crf', str(FFMPEG_CRF), '-preset', FFMPEG_PRESET,
                    '-acodec', 'aac', output_file
                ]

            logger.info(f"Merging with command: {' '.join(command)}")
            result = subprocess.run(command, capture_output=True, text=True)
            
            if result.returncode == 0 and os.path.exists(output_file):
                logger.info(f"Successfully merged: {output_file}")
                return True
            else:
                logger.error(f"FFmpeg Error: {result.stderr}")
                return False
        except Exception as e:
            logger.error(f"Merge Exception: {e}")
            return False
        finally:
            if os.path.exists(list_file):
                os.remove(list_file)

merger = Merger()
