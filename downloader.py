import asyncio
import httpx
import os
import logging
import time
from config import MAX_CONCURRENT_DOWNLOADS

logger = logging.getLogger(__name__)

class Downloader:
    def __init__(self):
        self.semaphore = asyncio.Semaphore(MAX_CONCURRENT_DOWNLOADS)
        self.retry_count = 3

    async def download_file(self, stream_info, dest_path, progress_callback=None):
        """Download HLS stream with DIRECT VTT Assembly & Progress Tracking"""
        async with self.semaphore:
            m3u8_url = stream_info.get("url")
            cookies_dict = stream_info.get("cookies", {})
            if not m3u8_url: return False

            cookie_str = "; ".join([f"{k}={v}" for k, v in cookies_dict.items()])
            user_agent = "Vigloo/1.1.0 (com.vigloo.android; build:110; Android 13; Model:SM-G998B)"

            # 1. Smart Subtitle Detection & Assembly
            srt_path = dest_path.replace(".mp4", ".srt")
            has_sub = False
            try:
                async with httpx.AsyncClient(headers={"User-Agent": user_agent}) as client:
                    r = await client.get(m3u8_url, cookies=cookies_dict, timeout=10.0)
                    if r.status_code == 200:
                        lines = r.text.splitlines()
                        sub_uri = None
                        for line in lines:
                            if 'TYPE=SUBTITLES' in line and ('"ind"' in line.lower() or '"id"' in line.lower()):
                                if 'URI="' in line: sub_uri = line.split('URI="')[1].split('"')[0]; break
                        if not sub_uri:
                            for line in lines:
                                if 'TYPE=SUBTITLES' in line and '"eng"' in line.lower():
                                    sub_uri = line.split('URI="')[1].split('"')[0]; break
                        
                        if sub_uri:
                            final_sub_url = sub_uri if sub_uri.startswith("http") else m3u8_url.rsplit("/", 1)[0] + "/" + sub_uri
                            r_sub = await client.get(final_sub_url, cookies=cookies_dict, timeout=10.0)
                            if r_sub.status_code == 200:
                                sub_lines = r_sub.text.splitlines()
                                bin_content = b""
                                base_sub_url = final_sub_url.rsplit("/", 1)[0] + "/"
                                segments = [l for l in sub_lines if l and not l.startswith("#")]
                                for s_line in segments:
                                    seg_url = s_line if s_line.startswith("http") else base_sub_url + s_line
                                    r_seg = await client.get(seg_url, cookies=cookies_dict, timeout=5.0)
                                    if r_seg.status_code == 200:
                                        bin_content += r_seg.content
                                
                                temp_bin = srt_path + ".tmp"
                                with open(temp_bin, "wb") as f: f.write(bin_content)
                                sub_cmd = ['ffmpeg', '-y', '-i', temp_bin, srt_path]
                                sub_proc = await asyncio.create_subprocess_exec(*sub_cmd, stderr=asyncio.subprocess.PIPE)
                                await sub_proc.communicate()
                                if os.path.exists(temp_bin): os.remove(temp_bin)
                                if os.path.exists(srt_path) and os.path.getsize(srt_path) > 100:
                                    has_sub = True
            except Exception as e:
                logger.warning(f"Sub Assembly failed: {e}")

            # 2. Probe total duration
            total_duration = 0
            try:
                probe_cmd = ['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', m3u8_url]
                process_probe = await asyncio.create_subprocess_exec(*probe_cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
                stdout_p, _ = await process_probe.communicate()
                total_duration = float(stdout_p.decode().strip()) if stdout_p else 0
            except: pass

            # 3. Download & Burn Video with Live Progress
            for attempt in range(self.retry_count):
                try:
                    command = ['ffmpeg', '-y', '-user_agent', user_agent, '-headers', f"Cookie: {cookie_str}\r\n", '-i', m3u8_url]
                    if has_sub:
                        escaped_srt = srt_path.replace("\\", "/").replace(":", "\\:")
                        command += ['-vf', f"subtitles='{escaped_srt}'", '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '24', '-c:a', 'copy']
                    else:
                        command += ['-c', 'copy']
                    command += ['-bsf:a', 'aac_adtstoasc', '-progress', 'pipe:2', dest_path]
                    
                    process = await asyncio.create_subprocess_exec(*command, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE)
                    
                    start_time = time.time()
                    last_update = 0
                    
                    while True:
                        line = await process.stderr.readline()
                        if not line: break
                        line_str = line.decode().strip()
                        
                        if progress_callback and "out_time_ms=" in line_str:
                            try:
                                time_ms = int(line_str.split("=")[1])
                                current_sec = time_ms / 1000000
                                # Update only every 2 seconds to avoid flood
                                if time.time() - last_update > 2:
                                    percent = min(99, (current_sec / total_duration) * 100) if total_duration > 0 else 50
                                    await progress_callback(percent, current_sec, total_duration)
                                    last_update = time.time()
                            except: pass

                    await process.wait()
                    if process.returncode == 0 and os.path.exists(dest_path) and os.path.getsize(dest_path) > 0:
                        if os.path.exists(srt_path): os.remove(srt_path)
                        return True
                except Exception as e:
                    logger.warning(f"Attempt {attempt+1} failed: {e}")
                await asyncio.sleep(5)
        return False

downloader = Downloader()
